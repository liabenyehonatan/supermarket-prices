import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from 'react';
import type { Basket, BasketSnapshot, LocalBasketItem } from '../types';

// Several named baskets; one is "active" and is the one every "add to basket" button feeds,
// the same model as an active cart in grocery apps.
interface BasketContextValue {
  baskets: Basket[];
  activeId: string;
  active: Basket;
  /** Items of the active basket — the rest of the app keeps using these. */
  items: LocalBasketItem[];
  addItem: (item: LocalBasketItem) => void;
  removeItem: (barcode: string) => void;
  updateQty: (barcode: string, qty: number) => void;
  clearBasket: () => void;
  totalItems: number;
  setActive: (id: string) => void;
  createBasket: (name?: string) => string;
  renameBasket: (id: string, name: string) => void;
  deleteBasket: (id: string) => void;
  /** The basket removed a moment ago, kept briefly so it can be restored. */
  lastDeleted: { basket: Basket; index: number } | null;
  undoDelete: () => void;
  recordCompare: (id: string, snapshot: BasketSnapshot) => void;
}

const BasketContext = createContext<BasketContextValue | null>(null);

const STORAGE_KEY = 'sali_baskets_v1';
const LEGACY_KEY = 'sali_basket';
export const BASKET_COLORS = ['#4D6B39', '#8A5A3C', '#3F7F7A', '#B08A2E', '#7C5A7A', '#5C6F8A'];

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function newBasket(name: string, colorIndex: number, items: LocalBasketItem[] = []): Basket {
  return { id: uid(), name, color: BASKET_COLORS[colorIndex % BASKET_COLORS.length], items };
}

interface Stored { activeId: string; baskets: Basket[] }

function load(): Stored {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const s = JSON.parse(raw) as Stored;
      if (Array.isArray(s.baskets) && s.baskets.length) {
        return { baskets: s.baskets, activeId: s.baskets.some(b => b.id === s.activeId) ? s.activeId : s.baskets[0].id };
      }
    }
  } catch { /* fall through to a fresh start */ }
  // First run with baskets: carry over the old single basket
  let legacy: LocalBasketItem[] = [];
  try { legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) ?? '[]') as LocalBasketItem[]; } catch { /* ignore */ }
  const first = newBasket('הסל שלי', 0, legacy);
  return { baskets: [first], activeId: first.id };
}

export function BasketProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Stored>(load);
  const stateRef = useRef(state);
  const [lastDeleted, setLastDeleted] = useState<{ basket: Basket; index: number } | null>(null);
  const undoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  stateRef.current = state;

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* storage blocked */ }
  }, [state]);

  // Keep several open tabs in step
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) setState(load());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const mapActive = useCallback((fn: (items: LocalBasketItem[]) => LocalBasketItem[]) => {
    setState(s => ({
      ...s,
      baskets: s.baskets.map(b => (b.id === s.activeId ? { ...b, items: fn(b.items) } : b)),
    }));
  }, []);

  const addItem = useCallback((item: LocalBasketItem) => {
    mapActive(prev => {
      const existing = prev.find(i => i.barcode === item.barcode);
      return existing
        ? prev.map(i => (i.barcode === item.barcode ? { ...i, quantity: i.quantity + item.quantity } : i))
        : [...prev, item];
    });
  }, [mapActive]);

  const removeItem = useCallback((barcode: string) => mapActive(prev => prev.filter(i => i.barcode !== barcode)), [mapActive]);

  const updateQty = useCallback((barcode: string, qty: number) => {
    mapActive(prev => qty <= 0
      ? prev.filter(i => i.barcode !== barcode)
      : prev.map(i => (i.barcode === barcode ? { ...i, quantity: qty } : i)));
  }, [mapActive]);

  const clearBasket = useCallback(() => mapActive(() => []), [mapActive]);

  const setActive = useCallback((id: string) => setState(s => (s.baskets.some(b => b.id === id) ? { ...s, activeId: id } : s)), []);

  const createBasket = useCallback((name?: string) => {
    const id = uid();
    setState(s => {
      const b = { ...newBasket(name?.trim() || 'סל חדש', s.baskets.length), id };
      return { baskets: [...s.baskets, b], activeId: id };
    });
    return id;
  }, []);

  const renameBasket = useCallback((id: string, name: string) => {
    const clean = name.trim();
    if (!clean) return;
    setState(s => ({ ...s, baskets: s.baskets.map(b => (b.id === id ? { ...b, name: clean } : b)) }));
  }, []);

  const deleteBasket = useCallback((id: string) => {
    const cur = stateRef.current;
    const index = cur.baskets.findIndex(b => b.id === id);
    if (index < 0) return;
    const basket = cur.baskets[index];
    setState(s => {
      let rest = s.baskets.filter(b => b.id !== id);
      if (!rest.length) rest = [newBasket('הסל שלי', 0)];
      return { baskets: rest, activeId: s.activeId === id ? rest[0].id : s.activeId };
    });
    setLastDeleted({ basket, index });
    if (undoTimer.current) clearTimeout(undoTimer.current);
    undoTimer.current = setTimeout(() => setLastDeleted(null), 6000);
  }, []);

  const restoreBasket = useCallback((basket: Basket, index: number) => {
    setState(s => {
      if (s.baskets.some(b => b.id === basket.id)) return s;
      // Undoing the delete of the only basket: drop the empty placeholder that replaced it
      const base = s.baskets.length === 1 && s.baskets[0].items.length === 0 && !s.baskets[0].lastCompare ? [] : s.baskets;
      const next = [...base];
      next.splice(Math.min(index, next.length), 0, basket);
      return { baskets: next, activeId: basket.id };
    });
  }, []);

  const undoDelete = useCallback(() => {
    setLastDeleted(d => {
      if (d) restoreBasket(d.basket, d.index);
      return null;
    });
  }, [restoreBasket]);

  const recordCompare = useCallback((id: string, snapshot: BasketSnapshot) => {
    setState(s => ({ ...s, baskets: s.baskets.map(b => (b.id === id ? { ...b, lastCompare: snapshot } : b)) }));
  }, []);

  const active = state.baskets.find(b => b.id === state.activeId) ?? state.baskets[0];
  const totalItems = active.items.reduce((sum, i) => sum + i.quantity, 0);

  const value = useMemo<BasketContextValue>(() => ({
    baskets: state.baskets, activeId: active.id, active, items: active.items,
    addItem, removeItem, updateQty, clearBasket, totalItems,
    setActive, createBasket, renameBasket, deleteBasket, lastDeleted, undoDelete, recordCompare,
  }), [state.baskets, active, totalItems, addItem, removeItem, updateQty, clearBasket,
       setActive, createBasket, renameBasket, deleteBasket, lastDeleted, undoDelete, recordCompare]);

  return <BasketContext.Provider value={value}>{children}</BasketContext.Provider>;
}

export function useBasket(): BasketContextValue {
  const ctx = useContext(BasketContext);
  if (!ctx) throw new Error('useBasket must be used inside BasketProvider');
  return ctx;
}
