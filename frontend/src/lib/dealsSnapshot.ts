import type { Deal } from '../api/client';

// The promotions page keeps what it shows (filters, the cards loaded so far, the scroll position) for a while, so going
// back from a product page lands on the same card instead of the top of the list. Same idea as the search results.

const KEY = 'sali_deals_snapshot';
const MAX_AGE_MS = 15 * 60 * 1000;

export interface DealsSnapshot {
  chain: string;
  sort: 'best' | 'ending';
  kind: '' | 'single' | 'group';
  city: string;
  deals: Deal[];
  total: number;
  chains: { name: string; count: number }[];
  scrollY: number;
  at: number;
}

/** The saved view, if it is recent, has cards and was made for the same city; otherwise null (load fresh). An empty list
 *  is never restored: it is what a failed load leaves behind. */
export function readDealsSnapshot(city: string): DealsSnapshot | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const snap = JSON.parse(raw) as DealsSnapshot;
    return snap.city === city && snap.deals.length > 0 && Date.now() - snap.at < MAX_AGE_MS ? snap : null;
  } catch {
    return null;
  }
}

export function writeDealsSnapshot(snap: Omit<DealsSnapshot, 'at'>) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ ...snap, at: Date.now() }));
  } catch {
    // storage full or blocked: going back just reloads the list
  }
}
