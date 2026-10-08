export interface Product {
  id: number;
  barcode: string;
  name: string;
  brand?: string;
  manufacturer?: string;
  category?: string;
  unit_of_measure?: string;
  image_url?: string;
}

export interface PriceAtStore {
  store_id: number;
  store_name: string;
  store_city?: string;
  store_address?: string;
  chain_name: string;
  price: number;
  unit_price?: number;
  price_updated_at?: string;
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

export interface ChainResponse {
  id: number;
  name: string;
  chain_id: string;
}

export interface StoreResponse {
  id: number;
  store_id: string;
  name: string;
  city?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  delivery_url?: string;
  chain: ChainResponse;
}

export interface ItemPrice {
  product_name: string;
  barcode: string;
  unit_price: number;
  quantity: number;
  line_total: number;
  missing?: boolean;
}

export interface BasketStoreTotal {
  store: StoreResponse;
  total_price: number;
  items_found: number;
  items_missing: number;
  item_prices: ItemPrice[];
}

export interface BasketCompareResponse {
  stores: BasketStoreTotal[];
  total_items_requested: number;
  cheapest_store: string;
  max_savings: number;
}

export interface LocalBasketItem {
  barcode: string;
  quantity: number;
  name: string;
  brand?: string;
  unit?: string;
}

/** What the cheapest comparison looked like the last time a basket was compared. */
export interface BasketSnapshot {
  at: number;          // epoch ms
  total: number;       // cheapest complete store total (falls back to the cheapest overall)
  chain: string;
  sig: string;         // basket contents at the time — a delta only makes sense for the same contents
  filterKey: string;   // city + chain filter at the time
}

export interface Basket {
  id: string;
  name: string;
  items: LocalBasketItem[];
  lastCompare?: BasketSnapshot;
}

export interface PriceHistoryPoint {
  date: string;   // YYYY-MM-DD
  price: string;  // Decimal serialized as string
}

export interface PriceHistoryResponse {
  barcode: string;
  days: number;
  points: PriceHistoryPoint[];
}
