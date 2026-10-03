const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Product {
  id: number;
  barcode: string;
  name: string;
  brand?: string;
  image_url?: string;
  unit_of_measure?: string;
  is_weighted: boolean;
}

export interface PriceAtStore {
  store_id: number;
  store_name?: string;
  store_city?: string;
  chain_name: string;
  price: number;
  unit_price?: number;
  price_updated_at: string;
  latitude?: number;
  longitude?: number;
  delivery_url?: string;
}

export interface ProductCompareResponse {
  product: Product;
  prices: PriceAtStore[];
  cheapest_price: number;
  most_expensive_price: number;
  price_difference: number;
}

export interface BasketStoreTotal {
  store: {
    id: number;
    store_id: string;
    name?: string;
    city?: string;
    address?: string;
    latitude?: number;
    longitude?: number;
    chain: { id: number; name: string; chain_id: string };
  };
  total_price: number;
  items_found: number;
  items_missing: number;
  item_prices: Array<{
    barcode: string;
    product_name: string;
    unit_price: number;
    quantity: number;
    line_total: number;
  }>;
}

export interface BasketCompareResponse {
  stores: BasketStoreTotal[];
  total_items_requested: number;
  cheapest_store?: string;
  max_savings: number;
}

export async function searchProducts(q: string, limit = 20): Promise<Product[]> {
  const res = await fetch(`${API_BASE}/api/v1/products/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  if (!res.ok) return [];
  return res.json();
}

export async function compareProduct(barcode: string): Promise<ProductCompareResponse | null> {
  const res = await fetch(`${API_BASE}/api/v1/products/${barcode}/compare`);
  if (!res.ok) return null;
  return res.json();
}

export async function compareBasket(
  items: Array<{ barcode: string; quantity: number }>
): Promise<BasketCompareResponse | null> {
  const res = await fetch(`${API_BASE}/api/v1/basket/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });
  if (!res.ok) return null;
  return res.json();
}
