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

export function searchProducts(q: string, limit = 20): Promise<Product[]> {
  return request<Product[]>(
    `/api/v1/products/search?q=${encodeURIComponent(q)}&limit=${limit}`
  );
}

export function compareProduct(barcode: string): Promise<ProductCompareResponse> {
  return request<ProductCompareResponse>(`/api/v1/products/${barcode}/compare`);
}

export function fetchCities(): Promise<string[]> {
  return request<string[]>('/api/v1/stores/cities');
}

export function compareBasket(
  items: { barcode: string; quantity: number }[]
): Promise<BasketCompareResponse> {
  return request<BasketCompareResponse>('/api/v1/basket/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(items),
  });
}
