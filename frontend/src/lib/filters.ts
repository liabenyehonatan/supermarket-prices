// Store filters (city + chain) shared by the home, product and basket pages.
// Kept in sessionStorage so a choice made on one page applies on the others.

export const FEATURED_CHAINS = [
  'שופרסל', 'רמי לוי', 'ויקטורי', 'מגה',
  'יוחננוף', 'טיב טעם', 'אושר עד', 'קרפור', 'חצי חינם',
];

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
