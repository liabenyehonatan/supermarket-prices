import type { BasketStoreTotal } from '../types';
import type { Coords } from './location';
import { distanceKm } from './geo';
import { isEilat } from './store';

export const NEAR_KM = 5;      // "near me" for the cheapest-branch mark

/** The branch marked as the cheapest: among the complete baskets in view (`inView`), the cheapest within NEAR_KM of the
 *  visitor, or, when none is that close (or the position is unknown), the cheapest in view. The overall cheapest is no
 *  use: Eilat has no VAT, so its branches always win and mean nothing elsewhere. `stores` is in comparison order, so the
 *  first match is the cheapest. The map's green pin and the list's "cheapest" badge both use this, so they always agree
 *  and the mark is always on screen. */
export function pickBest(stores: BasketStoreTotal[], me: Coords | null, inView: (s: BasketStoreTotal) => boolean): BasketStoreTotal | undefined {
  const visible = stores.filter(s => s.items_missing === 0 && s.store.latitude != null && s.store.longitude != null && inView(s));
  const near = me ? visible.filter(s => distanceKm(me.lat, me.lng, s.store.latitude!, s.store.longitude!) <= NEAR_KM) : visible;
  const pool = near.length ? near : visible;
  const withVat = pool.filter(s => !isEilat(s.store.city));
  return (withVat.length ? withVat : pool)[0];
}
