import { useCallback, useEffect, useState } from 'react';

export type LocationProblem = 'denied' | 'unavailable' | 'timeout' | 'unsupported' | 'no-city' | 'ask';
export type Coords = { lat: number; lng: number };

// The raw position is kept too (not just the city) so pages can show the
// distance to each geocoded store.
const COORDS_KEY = 'myCoords';
export function readMyCoords(): Coords | null {
  try {
    const raw = sessionStorage.getItem(COORDS_KEY);
    return raw ? JSON.parse(raw) as Coords : null;
  } catch { return null; }
}

/** Reverse-geocode coordinates to a Hebrew city name (OpenStreetMap Nominatim). */
async function cityFromCoords(lat: number, lon: number): Promise<string> {
  const res = await fetch(
    `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&accept-language=he`,
  );
  if (!res.ok) return '';
  const json = await res.json();
  const a = json.address ?? {};
  return a.city || a.town || a.village || a.suburb || '';
}

/**
 * Rough city from the IP address — no permission needed, only used as a
 * suggestion the user can accept. Reuses the Hebrew reverse-geocoder so the
 * name matches the city list.
 */
async function cityFromIp(): Promise<string> {
  const res = await fetch('https://ipwho.is/?fields=success,latitude,longitude');
  if (!res.ok) return '';
  const j = await res.json();
  if (!j.success) return '';
  return cityFromCoords(j.latitude, j.longitude);
}

const ASKED_KEY = 'locationSoftAsked';

/**
 * Finds the city of the user's current location.
 * When location services are off or blocked, `problem` is set so the page
 * can show the "turn on location" prompt.
 */
export function useCurrentCity(onCity: (city: string) => void, onCoords?: (coords: Coords) => void) {
  const [locating, setLocating] = useState(false);
  const [problem, setProblem] = useState<LocationProblem | null>(null);

  const [suggestedCity, setSuggestedCity] = useState('');

  // Whenever we land on a failure state, look up a quiet IP-based suggestion.
  useEffect(() => {
    if (!problem || problem === 'ask' || suggestedCity) return;
    let live = true;
    cityFromIp().then(c => { if (live) setSuggestedCity(c); }).catch(() => {});
    return () => { live = false; };
  }, [problem, suggestedCity]);

  /** The real browser/OS permission request. */
  const request = useCallback(() => {
    setProblem(null);
    if (!('geolocation' in navigator)) { setProblem('unsupported'); return; }
    try { sessionStorage.setItem(ASKED_KEY, '1'); } catch { /* storage blocked */ }
    setLocating(true);

    // Watchdog: if neither callback fires, don't leave the user hanging.
    let settled = false;
    const watchdog = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      setLocating(false);
      setProblem('unavailable');
    }, 15000);

    navigator.geolocation.getCurrentPosition(
      async pos => {
        if (settled) return;
        settled = true;
        window.clearTimeout(watchdog);
        const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        try { sessionStorage.setItem(COORDS_KEY, JSON.stringify(coords)); } catch { /* storage blocked */ }
        onCoords?.(coords);
        try {
          const city = await cityFromCoords(pos.coords.latitude, pos.coords.longitude);
          if (city) onCity(city);
          else setProblem('no-city');
        } catch {
          setProblem('no-city');
        } finally {
          setLocating(false);
        }
      },
      err => {
        if (settled) return;
        settled = true;
        window.clearTimeout(watchdog);
        setLocating(false);
        setProblem(
          err.code === err.PERMISSION_DENIED ? 'denied'
            : err.code === err.TIMEOUT ? 'timeout'
              : 'unavailable',
        );
      },
      { timeout: 10000, maximumAge: 5 * 60 * 1000 },
    );
  }, [onCity, onCoords]);

  /**
   * Entry point. Shows our own explainer first when the browser would pop its
   * one-shot system dialog (a "Don't allow" there can't be re-asked), and goes
   * straight to the failure screen when access is already blocked.
   */
  const locate = useCallback(async () => {
    setProblem(null);
    if (!('geolocation' in navigator)) { setProblem('unsupported'); return; }
    let state: PermissionState | undefined;
    try {
      state = (await navigator.permissions?.query({ name: 'geolocation' }))?.state;
    } catch { /* Permissions API unsupported for geolocation */ }
    if (state === 'denied') { setProblem('denied'); return; }
    let asked = false;
    try { asked = sessionStorage.getItem(ASKED_KEY) === '1'; } catch { /* storage blocked */ }
    if (state === 'granted' || asked) { request(); return; }
    setProblem('ask');
  }, [request]);

  /** Manual fallback: the user picked a city themselves. */
  const pickCity = useCallback((city: string) => {
    setProblem(null);
    if (city) onCity(city);
  }, [onCity]);

  const dismiss = useCallback(() => setProblem(null), []);

  return { locate, request, pickCity, suggestedCity, locating, problem, dismiss };
}
