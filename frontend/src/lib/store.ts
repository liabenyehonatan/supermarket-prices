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

const URLISH = /(https?:\/\/|www\.|\.(co\.il|org\.il|com|org|net)\b)/i;
const ONLINE_WORD = /(online|אונליין)/i;
const ONLINE_NAME = /(online|אונליין|אינטרנט)/i;

/** An address with a web link stuck on the end ("דרך הדרום http:// 1") loses the link. */
function cleanAddress(raw?: string | null): string {
  const a = (raw ?? '').trim();
  if (!a) return '';
  const cut = a.replace(/\s*(https?:\/\/\S*|www\.\S*|\S+\.(co\.il|org\.il|com|org|net)\S*)[\s\d|/]*$/i, '').replace(/[\s|]+$/, '').trim();
  return cut.length > 1 ? cut : '';
}

/** Chains list their web shop as a "store": its name says online/internet, or its "address" is just a web link. */
export function isOnlineStore(s: StoreText): boolean {
  if (ONLINE_NAME.test(s.name ?? '')) return true;
  const raw = (s.address ?? '').trim();
  return !!raw && URLISH.test(raw) && cleanAddress(raw) === '';
}

/** The branch name when it says more than the chain name, otherwise ''.
 *  A web shop is always named "<chain> אונליין" (unless its own name already says so). */
export function storeBranch(s: StoreText): string {
  const n = (s.name ?? '').trim();
  if (isOnlineStore(s)) return ONLINE_WORD.test(n) ? n : `${s.chain} אונליין`;
  return n && n !== s.chain ? n : '';
}

/** "address, city" with junk values dropped; a web shop's address is simply "אינטרנט". */
export function storeAddress(s: StoreText): string {
  if (isOnlineStore(s)) return 'אינטרנט';
  return unique([cleanAddress(s.address), cityName(s.city)]).join(', ');
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

/** Navigate-to links for a branch (both take a free-text destination). */
export function wazeLink(s: StoreText): string {
  return `https://waze.com/ul?q=${encodeURIComponent(navQuery(s) || s.chain)}&navigate=yes`;
}
export function googleMapsLink(s: StoreText): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(navQuery(s) || s.chain)}`;
}

/** Eilat sells without VAT, so its prices run about a sixth lower than everywhere else and always come out cheapest. */
export function isEilat(city?: string | null): boolean {
  return (city ?? '').includes('אילת');
}

export const EILAT_NOTE = 'אילת: המחיר בלי מע״מ, לא להשוואה לשאר הארץ';

/** Puts Eilat after everything else of the same tier (stable, so the price order is kept), unless nothing else is
 *  listed. `tier` is what must stay first regardless (a basket missing items is always after a full one). */
export function eilatLast<T>(rows: T[], cityOf: (row: T) => string | null | undefined, tierOf: (row: T) => number = () => 0): T[] {
  if (rows.every(r => isEilat(cityOf(r)))) return rows;
  return [...rows].sort((a, b) => tierOf(a) - tierOf(b) || Number(isEilat(cityOf(a))) - Number(isEilat(cityOf(b))));
}
