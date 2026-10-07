import { useCallback, useState } from 'react';

export type LocationProblem = 'denied' | 'unavailable' | 'timeout' | 'unsupported' | 'no-city';
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
 * Finds the city of the user's current location.
 * When location services are off or blocked, `problem` is set so the page
 * can show the "turn on location" prompt.
 */
export function useCurrentCity(onCity: (city: string) => void, onCoords?: (coords: Coords) => void) {
  const [locating, setLocating] = useState(false);
  const [problem, setProblem] = useState<LocationProblem | null>(null);

  const locate = useCallback(() => {
    setProblem(null);
    if (!('geolocation' in navigator)) { setProblem('unsupported'); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async pos => {
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

  const dismiss = useCallback(() => setProblem(null), []);

  return { locate, locating, problem, dismiss };
}
