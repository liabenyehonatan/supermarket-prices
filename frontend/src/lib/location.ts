import { useCallback, useState } from 'react';

export type LocationProblem = 'denied' | 'unavailable' | 'timeout' | 'unsupported' | 'no-city';

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
export function useCurrentCity(onCity: (city: string, coords: { lat: number; lng: number }) => void) {
  const [locating, setLocating] = useState(false);
  const [problem, setProblem] = useState<LocationProblem | null>(null);

  const locate = useCallback(() => {
    setProblem(null);
    if (!('geolocation' in navigator)) { setProblem('unsupported'); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async pos => {
        const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        try {
          const city = await cityFromCoords(coords.lat, coords.lng);
          if (city) onCity(city, coords);
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
  }, [onCity]);

  const dismiss = useCallback(() => setProblem(null), []);

  return { locate, locating, problem, dismiss };
}
