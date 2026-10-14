import type {
  Product,
  ProductCompareResponse,
  BasketCompareResponse,
} from '../types';

// Empty = same origin (the production default). The dev server proxies /api (see vite.config.ts).
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? '';

/** A failed API call; `status` lets callers tell "not found" (404) from "server unreachable". */
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new ApiError(res.status, text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

import { cityName } from '../lib/store';
export function searchProducts(q: string, limit = 20, offset = 0): Promise<Product[]> {
  return request<Product[]>(
    `/api/v1/products/search?q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`
  );
}

export function compareProduct(barcode: string): Promise<ProductCompareResponse> {
  return request<ProductCompareResponse>(`/api/v1/products/${barcode}/compare`);
}

// Cheapest current price for many barcodes in one request — used by the search
// results list, instead of one /compare call per visible product.
export function cheapestPricesBatch(barcodes: string[]): Promise<Record<string, number>> {
  if (barcodes.length === 0) return Promise.resolve({});
  return request<Record<string, number>>('/api/v1/products/cheapest-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ barcodes }),
  });
}

export interface DataStats { chains: number; stores: number; products: number; last_updated: string | null }

let statsRequest: Promise<DataStats> | null = null;

/** Totals and the last refresh time, shared by one request per page load. */
export function fetchStats(): Promise<DataStats> {
  if (!statsRequest) {
    statsRequest = request<DataStats>('/api/v1/stats').catch(err => {
      statsRequest = null;
      throw err;
    });
  }
  return statsRequest;
}

export interface UnitPriceInfo { unit_price: number | string; unit?: string | null }

export function fetchUnitPrices(barcodes: string[]): Promise<Record<string, UnitPriceInfo>> {
  if (barcodes.length === 0) return Promise.resolve({});
  return request<Record<string, UnitPriceInfo>>('/api/v1/products/unit-prices-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ barcodes }),
  });
}

export interface ExampleComparison {
  barcode: string; name: string; brand?: string; unit_of_measure?: string;
  cheapest_price: number | string; cheapest_chain: string;
  priciest_price: number | string; priciest_chain: string; stores_count: number;
}

export interface DealProduct { barcode: string; name: string; brand?: string; image_url?: string; unit_of_measure?: string }
export interface Deal {
  deal_id: string; brand: string; description: string; kind: 'single' | 'group';
  min_qty: number; price: number | string; unit_price: number | string; ref_price: number | string;
  saving_pct: number | string;            // a fraction: 0.25 is 25%
  stores: number; products: number; max_qty?: number | null; ends_at?: string | null; sample_products: DealProduct[];
}
export interface DealsResponse { total: number; deals: Deal[]; chains: { name: string; count: number }[] }

export function fetchDeals(p: {
  chain?: string; city?: string; kind?: 'single' | 'group'; sort?: 'best' | 'ending'; diverse?: boolean; limit?: number; offset?: number;
} = {}): Promise<DealsResponse> {
  const q = new URLSearchParams();
  if (p.chain) q.set('chain', p.chain);
  if (p.city) q.set('city', p.city);
  if (p.kind) q.set('kind', p.kind);
  if (p.sort) q.set('sort', p.sort);
  if (p.diverse) q.set('diverse', 'true');
  if (p.limit) q.set('limit', String(p.limit));
  if (p.offset) q.set('offset', String(p.offset));
  return request<DealsResponse>(`/api/v1/deals?${q.toString()}`);
}
export function fetchDealProducts(dealId: string): Promise<DealProduct[]> {
  return request<DealProduct[]>(`/api/v1/deals/${encodeURIComponent(dealId)}/products`);
}

/** The city nearest to a position, answered by our own server from the stores we hold. The position is
 *  rounded to ~1 km before it leaves the phone; nothing is sent to a third party. */
export async function fetchNearestCity(lat: number, lng: number): Promise<string> {
  const r = await request<{ city: string | null }>(`/api/v1/location/city?lat=${lat.toFixed(2)}&lng=${lng.toFixed(2)}`);
  return r.city ?? '';
}

export function fetchChains(): Promise<{ name: string; stores: number }[]> {
  return request<{ name: string; stores: number }[]>('/api/v1/chains');
}

export function fetchExamples(limit = 3): Promise<ExampleComparison[]> {
  return request<ExampleComparison[]>(`/api/v1/products/examples?limit=${limit}`);
}

// The city list rarely changes, so share one request per page load.
// (Dev StrictMode runs effects twice, which used to fire this call twice.)
let citiesRequest: Promise<string[]> | null = null;

export function fetchCities(): Promise<string[]> {
  if (!citiesRequest) {
    citiesRequest = request<string[]>('/api/v1/stores/cities')
      .then(list => list.filter(c => cityName(c)))   // chains publish numeric city codes too
      .catch(err => {
      citiesRequest = null; // allow a retry after a failure
      throw err;
    });
  }
  return citiesRequest;
}

export function compareBasket(
  items: { barcode: string; quantity: number }[],
  filters: { city?: string; chain?: string } = {}
): Promise<BasketCompareResponse> {
  const params = new URLSearchParams();
  if (filters.city?.trim()) params.set('city', filters.city.trim());
  if (filters.chain?.trim()) params.set('chain', filters.chain.trim());
  params.set('limit', '100');          // the best 100 stores are plenty to show; the full list is ~1.3 MB
  const qs = params.toString();
  return request<BasketCompareResponse>(`/api/v1/basket/compare${qs ? `?${qs}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(items),
  });
}
