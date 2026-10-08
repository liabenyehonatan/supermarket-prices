import { useEffect, useMemo, useState } from 'react';
import { compareBasket } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { basketSig, snapshotFrom } from './basketCompare';

export interface WatchResult { diff: number; now: number }

const TTL_MS = 30 * 60 * 1000;
const KEY = (id: string) => `sali_watch_${id}`;

interface Cached extends WatchResult { against: number; at: number }

function readCache(id: string, against: number): WatchResult | null {
  try {
    const c = JSON.parse(sessionStorage.getItem(KEY(id)) ?? 'null') as Cached | null;
    if (c && c.against === against && Date.now() - c.at < TTL_MS) return { diff: c.diff, now: c.now };
  } catch { /* ignore */ }
  return null;
}

/**
 * Quietly re-prices every basket that was compared before (same contents, same filters) and reports how
 * far the cheapest total has moved since the person last looked. It runs when the app is open — there is
 * no push, because nothing is stored on a server — and at most once per basket per half hour.
 * The baseline stays the last comparison the person saw, so the change remains until they compare again.
 */
export function useBasketWatch(): Record<string, WatchResult> {
  const { baskets } = useBasket();
  const [found, setFound] = useState<Record<string, WatchResult>>({});

  // Only re-run when something that affects a basket's price changes
  const signature = useMemo(
    () => baskets.map(b => `${b.id}:${basketSig(b.items)}:${b.lastCompare?.at ?? ''}`).join('|'),
    [baskets],
  );

  useEffect(() => {
    let live = true;
    baskets.forEach(b => {
      const last = b.lastCompare;
      if (!last || b.items.length === 0 || basketSig(b.items) !== last.sig) return;
      const cached = readCache(b.id, last.at);
      if (cached) { setFound(f => ({ ...f, [b.id]: cached })); return; }
      const [city = '', chain = ''] = last.filterKey.split('|');
      compareBasket(b.items.map(i => ({ barcode: i.barcode, quantity: i.quantity })), { city, chain })
        .then(res => {
          const snap = snapshotFrom(res, b.items, { city, chain });
          if (!snap || !live) return;
          const result = { diff: snap.total - last.total, now: snap.total };
          try { sessionStorage.setItem(KEY(b.id), JSON.stringify({ ...result, against: last.at, at: Date.now() })); } catch { /* ignore */ }
          setFound(f => ({ ...f, [b.id]: result }));
        })
        .catch(() => {});
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  return found;
}
