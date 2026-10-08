// Recently opened products, kept on the device so the home screen can offer a quick way back.
import type { Product } from '../types';

export type RecentProduct = Pick<Product, 'barcode' | 'name' | 'brand' | 'unit_of_measure'>;

const KEY = 'sali_recent_products';
const MAX = 5;

export function readRecent(): RecentProduct[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as RecentProduct[]).slice(0, MAX) : [];
  } catch { return []; }
}

export function pushRecent(p: RecentProduct) {
  try {
    const next = [
      { barcode: p.barcode, name: p.name, brand: p.brand, unit_of_measure: p.unit_of_measure },
      ...readRecent().filter(r => r.barcode !== p.barcode),
    ].slice(0, MAX);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // storage blocked — the list just won't persist
  }
}
