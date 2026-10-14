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

export interface PromoInfo {
  description: string;
  min_qty?: number;
  ends_at?: string;
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
  scraped_at?: string;
  latitude?: number;
  longitude?: number;
  delivery_url?: string;
  promotions?: PromoInfo[];
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

export interface ItemPromo {
  description: string;
  min_qty: number;
  price: number | string;
  sets: number;
}

export interface ItemPrice {
  product_name: string;
  barcode: string;
  unit_price: number;
  quantity: number;
  line_total: number;
  missing?: boolean;
  regular_line_total?: number | string;
  promo?: ItemPromo | null;
}

export interface PromoAdjustment {
  description: string;
  min_qty: number;
  price: number | string;
  sets: number;
  saving: number | string;
  barcodes: string[];
}

export interface BasketStoreTotal {
  store: StoreResponse;
  total_price: number;
  items_found: number;
  items_missing: number;
  item_prices: ItemPrice[];
  /** What promotions took off this store's shelf total, and whether we hold fresh promotion data for it. */
  savings?: number | string;
  promotions_known?: boolean;
  promo_adjustments?: PromoAdjustment[];
}

export interface BasketCompareResponse {
  stores: BasketStoreTotal[];
  total_items_requested: number;
  cheapest_store: string;
  max_savings: number;
  /** All matching stores (the list above is cut to the best N) and the highest total among complete baskets. */
  total_stores?: number;
  max_total?: number | string;
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
