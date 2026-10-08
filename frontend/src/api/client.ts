import type {
  Product,
  ProductCompareResponse,
  BasketCompareResponse,
} from '../types';

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

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

export function fetchExamples(limit = 3): Promise<ExampleComparison[]> {
  return request<ExampleComparison[]>(`/api/v1/products/examples?limit=${limit}`);
}

// The city list rarely changes, so share one request per page load.
// (Dev StrictMode runs effects twice, which used to fire this call twice.)
let citiesRequest: Promise<string[]> | null = null;

export function fetchCities(): Promise<string[]> {
  if (!citiesRequest) {
    citiesRequest = request<string[]>('/api/v1/stores/cities').catch(err => {
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
  const qs = params.toString();
  return request<BasketCompareResponse>(`/api/v1/basket/compare${qs ? `?${qs}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(items),
  });
}
