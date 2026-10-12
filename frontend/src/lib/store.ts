// How a store is described in the UI. Chains publish messy store data: the
// "city" is often a numeric CBS code ("2600"), "0" or "unknown", and the store
// name is frequently just the branch or town. Show the chain first, the branch name
// under it (the address when the row is opened), and never show a city that is not a name.

/** The city if it is a real name, otherwise ''. */
export function cityName(city?: string | null): string {
  const c = (city ?? '').trim();
  if (!c || /^\d+$/.test(c) || c.toLowerCase() === 'unknown') return '';
  return c;
}

interface StoreText { chain: string; name?: string | null; address?: string | null; city?: string | null }

function unique(parts: (string | null | undefined)[]): string[] {
  const out: string[] = [];
  for (const p of parts) {
    const t = (p ?? '').trim();
    if (t && t.toLowerCase() !== 'unknown' &&!out.some(o => o.includes(t) || t.includes(o))) out.push(t);
  }
  return out;
}

/** The branch name when it says more than the chain name, otherwise ''. */
export function storeBranch(s: StoreText): string {
  const n = (s.name ?? '').trim();
  return n && n !== s.chain ? n : '';
}

/** "address, city" with junk values dropped, or ''. */
export function storeAddress(s: StoreText): string {
  return unique([s.address, cityName(s.city)]).join(', ');
}

/** Line under the chain name: "סניף: <name>" (the address is shown when the row is opened);
 *  falls back to the address when the chain publishes no branch name. */
export function storeSubtitle(s: StoreText): string {
  const branch = storeBranch(s);
  return branch ? `סניף: ${branch}` : storeAddress(s);
}

/** Free-text destination for Waze / Google Maps. */
export function navQuery(s: StoreText): string {
  return unique([s.chain, s.name, s.address, cityName(s.city)]).join(', ');
}
