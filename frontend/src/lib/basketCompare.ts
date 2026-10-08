import type { Basket, BasketCompareResponse, BasketSnapshot } from '../types';

/** Same contents ⇒ same signature, so a price change can be told apart from an edited basket. */
export function basketSig(items: Basket['items']): string {
  return [...items].map(i => `${i.barcode}x${i.quantity}`).sort().join(',');
}

export function snapshotFrom(
  res: BasketCompareResponse, items: Basket['items'], filters: { city: string; chain: string },
): BasketSnapshot | null {
  if (!res.stores.length) return null;
  const pick = res.stores.filter(s => s.items_missing === 0).sort((a, b) => a.total_price - b.total_price)[0] ?? res.stores[0];
  return {
    at: Date.now(),
    total: Number(pick.total_price),
    chain: pick.store.chain?.name ?? '',
    sig: basketSig(items),
    filterKey: `${filters.city}|${filters.chain}`,
  };
}

export function timeAgo(ms: number): string {
  const min = Math.floor((Date.now() - ms) / 60000);
  if (min < 1) return 'ממש עכשיו';
  if (min < 60) return `לפני ${min} דק׳`;
  const h = Math.floor(min / 60);
  if (h < 24) return h === 1 ? 'לפני שעה' : `לפני ${h} שעות`;
  const d = Math.floor(h / 24);
  if (d === 1) return 'אתמול';
  if (d < 30) return `לפני ${d} ימים`;
  const m = Math.floor(d / 30);
  return m === 1 ? 'לפני חודש' : `לפני ${m} חודשים`;
}
