import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { LocalBasketItem } from '../types';

interface BasketContextValue {
  items: LocalBasketItem[];
  addItem: (item: LocalBasketItem) => void;
  removeItem: (barcode: string) => void;
  updateQty: (barcode: string, qty: number) => void;
  clearBasket: () => void;
  totalItems: number;
}

const BasketContext = createContext<BasketContextValue | null>(null);

const STORAGE_KEY = 'sali_basket';

function loadFromStorage(): LocalBasketItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw) as LocalBasketItem[];
  } catch {
    // ignore
  }
  return [];
}

export function BasketProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<LocalBasketItem[]>(loadFromStorage);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }, [items]);

  const addItem = useCallback((item: LocalBasketItem) => {
    setItems(prev => {
      const existing = prev.find(i => i.barcode === item.barcode);
      if (existing) {
        return prev.map(i =>
          i.barcode === item.barcode ? { ...i, quantity: i.quantity + item.quantity } : i
        );
      }
      return [...prev, item];
    });
  }, []);

  const removeItem = useCallback((barcode: string) => {
    setItems(prev => prev.filter(i => i.barcode !== barcode));
  }, []);

  const updateQty = useCallback((barcode: string, qty: number) => {
    if (qty <= 0) {
      setItems(prev => prev.filter(i => i.barcode !== barcode));
    } else {
      setItems(prev => prev.map(i => (i.barcode === barcode ? { ...i, quantity: qty } : i)));
    }
  }, []);

  const clearBasket = useCallback(() => setItems([]), []);

  const totalItems = items.reduce((sum, i) => sum + i.quantity, 0);

  return (
    <BasketContext.Provider value={{ items, addItem, removeItem, updateQty, clearBasket, totalItems }}>
      {children}
    </BasketContext.Provider>
  );
}

export function useBasket(): BasketContextValue {
  const ctx = useContext(BasketContext);
  if (!ctx) throw new Error('useBasket must be used inside BasketProvider');
  return ctx;
}
