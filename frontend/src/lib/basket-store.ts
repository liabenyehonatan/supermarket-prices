"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface BasketItem {
  barcode: string;
  name: string;
  brand?: string;
  imageUrl?: string;
  quantity: number;
}

interface BasketStore {
  items: BasketItem[];
  addItem: (item: Omit<BasketItem, "quantity">) => void;
  removeItem: (barcode: string) => void;
  updateQuantity: (barcode: string, quantity: number) => void;
  clearBasket: () => void;
}

export const useBasket = create<BasketStore>()(
  persist(
    (set) => ({
      items: [],
      addItem: (item) =>
        set((state) => {
          const existing = state.items.find((i) => i.barcode === item.barcode);
          if (existing) {
            return {
              items: state.items.map((i) =>
                i.barcode === item.barcode ? { ...i, quantity: i.quantity + 1 } : i
              ),
            };
          }
          return { items: [...state.items, { ...item, quantity: 1 }] };
        }),
      removeItem: (barcode) =>
        set((state) => ({ items: state.items.filter((i) => i.barcode !== barcode) })),
      updateQuantity: (barcode, quantity) =>
        set((state) => ({
          items: quantity <= 0
            ? state.items.filter((i) => i.barcode !== barcode)
            : state.items.map((i) => (i.barcode === barcode ? { ...i, quantity } : i)),
        })),
      clearBasket: () => set({ items: [] }),
    }),
    { name: "machirista-basket" }
  )
);
