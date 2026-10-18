import { useEffect, useState } from 'react';
import { fetchChains } from '../api/client';

// Store filters (city + chain) shared by the home, product and basket pages.
// Kept in sessionStorage so a choice made on one page applies on the others.

// Fallback list, used until (or if) the API's /chains answers. Chain names exactly as the parser stores them (CHAIN_DISPLAY_NAMES in
// app/parser/universal_parser.py): the API filters on an exact name match.
export const FEATURED_CHAINS = [
  'שופרסל', 'רמי לוי', 'ויקטורי', 'יוחננוף', 'טיב טעם', 'אושר עד', 'חצי חינם',
  'יינות ביתן', 'קרפור', 'דור אלון', 'פרשמרקט / סופרדוש', 'סיטי מרקט', 'סופר יודה',
  'סופר ספיר', 'סטופ מרקט', 'סאלח דבאח', 'זול ובגדול', 'מחסני השוק', 'מעיין 2000',
  'קינג סטור', 'קשת טעמים', 'שוק העיר', 'פוליצר', 'משנת יוסף',
  'עוף והודו ברקת', 'גוד פארם', 'שפע ברכת השם', 'יילו', 'וולט',
];

/**
 * The chains the app knows, biggest first, straight from the API (so it never drifts from the data).
 * With a city, only the chains that have a store there. `ready` is true once the list is the API's answer
 * for that city (not the fallback, nor the previous city's list).
 */
export function useCityChains(city = ''): { names: string[]; ready: boolean } {
  const [state, setState] = useState<{ city: string; names: string[] | null }>({ city, names: null });
  useEffect(() => {
    let live = true;
    fetchChains(city)
      .then(list => { if (live && (list.length || city)) setState({ city, names: list.map(c => c.name) }); })
      .catch(() => {});
    return () => { live = false; };
  }, [city]);
  const ready = state.names !== null && state.city === city;
  return { names: state.names ?? FEATURED_CHAINS, ready };
}

export function useChainNames(city = ''): string[] {
  return useCityChains(city).names;
}

const CITY_KEY = 'cityFilter';
const CHAIN_KEY = 'chainFilter';

function read(key: string): string {
  try { return sessionStorage.getItem(key) ?? ''; } catch { return ''; }
}

const CITY_EVENT = 'cityfilterchange';

function write(key: string, value: string) {
  const changed = read(key) !== value;
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    // storage blocked — the filter just won't carry over to other pages
  }
  if (changed && key === CITY_KEY) window.dispatchEvent(new Event(CITY_EVENT));
}

/** Lets pages follow a city change made elsewhere (e.g. the header chip). Returns an unsubscribe. */
export function onCityFilterChange(cb: (city: string) => void): () => void {
  const handler = () => cb(read(CITY_KEY));
  window.addEventListener(CITY_EVENT, handler);
  return () => window.removeEventListener(CITY_EVENT, handler);
}

export const readCityFilter  = () => read(CITY_KEY);
export const readChainFilter = () => read(CHAIN_KEY);
export const saveCityFilter  = (city: string) => write(CITY_KEY, city);
export const saveChainFilter = (chain: string) => write(CHAIN_KEY, chain);

/** Map a geocoded city name onto the closest name in our store city list. */
export function matchCity(found: string, cities: string[]): string {
  if (!found || !cities.length) return found;
  return cities.find(c => c === found)
    ?? cities.find(c => c.includes(found) || found.includes(c))
    ?? found;
}
