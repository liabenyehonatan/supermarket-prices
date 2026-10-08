import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from 'react';
import type { Basket, BasketSnapshot, LocalBasketItem } from '../types';

// Several named baskets; one is "active" and is the one every "add to basket" button feeds,
// the same model as an active cart in grocery apps.
export interface Notice { text: string; actionLabel?: string; onAction?: () => void }
export type PickerState =
  | { mode: 'add'; item: LocalBasketItem }
  | { mode: 'move'; items: LocalBasketItem[]; fromId: string }
  | { mode: 'create' }
  | null;

interface BasketContextValue {
  baskets: Basket[];
  activeId: string;
  active: Basket;
  /** Items of the active basket — the rest of the app keeps using these. */
  items: LocalBasketItem[];
  /** Adds to the active basket; with several baskets, the first add of a visit asks which one. */
  addItem: (item: LocalBasketItem) => void;
  removeItem: (barcode: string) => void;
  /** Removes several items at once; one "undo" brings them all back. */
  removeItems: (barcodes: string[]) => void;
  updateQty: (barcode: string, qty: number) => void;
  clearBasket: () => void;
  totalItems: number;
  setActive: (id: string) => void;
  createBasket: (name?: string) => string;
  renameBasket: (id: string, name: string) => void;
  deleteBasket: (id: string) => void;
  recordCompare: (id: string, snapshot: BasketSnapshot) => void;
  /** Short message shown at the bottom ("added to …", "deleted … · undo"). */
  notice: Notice | null;
  dismissNotice: () => void;
  picker: PickerState;
  openCreate: () => void;
  /** Opens the picker to send items of one basket to another. */
  openMove: (items: LocalBasketItem[], fromId: string) => void;
  closePicker: () => void;
  pickBasket: (id: string) => void;
  pickNew: (name: string) => void;
}

const BasketContext = createContext<BasketContextValue | null>(null);

const STORAGE_KEY = 'sali_baskets_v1';
const LEGACY_KEY = 'sali_basket';
// Set once the user has consciously picked a basket during this visit (tab session)
const CHOSEN_KEY = 'sali_basket_chosen';

function uid() {
  return Math.random().toString(36).slice(2, 10);
}

function newBasket(name: string, items: LocalBasketItem[] = []): Basket {
  return { id: uid(), name, items };
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
  const first = newBasket('הסל שלי', legacy);
  return { baskets: [first], activeId: first.id };
}

export function BasketProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Stored>(load);
  const stateRef = useRef(state);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [picker, setPicker] = useState<PickerState>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chosen = useRef((() => { try { return sessionStorage.getItem(CHOSEN_KEY) === '1'; } catch { return false; } })());

  const markChosen = useCallback(() => {
    chosen.current = true;
    try { sessionStorage.setItem(CHOSEN_KEY, '1'); } catch { /* storage blocked — we just ask again next time */ }
  }, []);

  const showNotice = useCallback((n: Notice, ms = 5000) => {
    setNotice(n);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), ms);
  }, []);
  const dismissNotice = useCallback(() => setNotice(null), []);
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

  const putInBasket = useCallback((basketId: string, item: LocalBasketItem) => {
    setState(s => ({
      activeId: basketId,
      baskets: s.baskets.map(b => {
        if (b.id !== basketId) return b;
        const existing = b.items.find(i => i.barcode === item.barcode);
        return {
          ...b,
          items: existing
            ? b.items.map(i => (i.barcode === item.barcode ? { ...i, quantity: i.quantity + item.quantity } : i))
            : [...b.items, item],
        };
      }),
    }));
  }, []);

  /** Adds to a basket and makes it the active one. No notice: the header pill shows where things go. */
  const addTo = useCallback((basketId: string, item: LocalBasketItem) => {
    putInBasket(basketId, item);
    markChosen();
  }, [putInBasket, markChosen]);

  const addItem = useCallback((item: LocalBasketItem) => {
    const cur = stateRef.current;
    if (cur.baskets.length > 1 && !chosen.current) { setPicker({ mode: 'add', item }); return; }
    const target = cur.baskets.find(b => b.id === cur.activeId) ?? cur.baskets[0];
    addTo(target.id, item);
  }, [addTo]);

  const restoreItems = useCallback((basketId: string, entries: { item: LocalBasketItem; index: number }[]) => {
    setState(st => ({
      ...st,
      baskets: st.baskets.map(b => {
        if (b.id !== basketId) return b;
        const items = [...b.items];
        [...entries].sort((a, c) => a.index - c.index).forEach(({ item, index }) => {
          if (items.some(i => i.barcode === item.barcode)) return;
          items.splice(Math.min(index, items.length), 0, item);
        });
        return { ...b, items };
      }),
    }));
  }, []);

  // Removal is always undoable: the removed items go back where they were
  const removeItems = useCallback((barcodes: string[]) => {
    const cur = stateRef.current;
    const basket = cur.baskets.find(b => b.id === cur.activeId);
    if (!basket) return;
    const gone = basket.items
      .map((item, index) => ({ item, index }))
      .filter(e => barcodes.includes(e.item.barcode));
    if (!gone.length) return;
    mapActive(prev => prev.filter(i => !barcodes.includes(i.barcode)));
    showNotice({
      text: gone.length === 1 ? `"${gone[0].item.name}" הוסר מהסל` : `${gone.length} מוצרים הוסרו מהסל`,
      actionLabel: 'ביטול',
      onAction: () => { restoreItems(basket.id, gone); setNotice(null); },
    }, 6000);
  }, [mapActive, showNotice, restoreItems]);
  const removeItem = useCallback((barcode: string) => removeItems([barcode]), [removeItems]);

  const updateQty = useCallback((barcode: string, qty: number) => {
    mapActive(prev => qty <= 0
      ? prev.filter(i => i.barcode !== barcode)
      : prev.map(i => (i.barcode === barcode ? { ...i, quantity: qty } : i)));
  }, [mapActive]);

  const clearBasket = useCallback(() => {
    const cur = stateRef.current;
    const basket = cur.baskets.find(b => b.id === cur.activeId);
    if (!basket || !basket.items.length) return;
    removeItems(basket.items.map(i => i.barcode));
  }, [removeItems]);

  const setActive = useCallback((id: string) => {
    setState(s => (s.baskets.some(b => b.id === id) ? { ...s, activeId: id } : s));
    markChosen();
  }, [markChosen]);

  const createBasket = useCallback((name?: string) => {
    const id = uid();
    const label = name?.trim() || 'סל חדש';
    setState(s => ({ baskets: [...s.baskets, { ...newBasket(label), id }], activeId: id }));
    markChosen();
    showNotice({ text: `מוסיפים עכשיו ל"${label}"` });
    return id;
  }, [markChosen, showNotice]);

  const renameBasket = useCallback((id: string, name: string) => {
    const clean = name.trim();
    if (!clean) return;
    setState(s => ({ ...s, baskets: s.baskets.map(b => (b.id === id ? { ...b, name: clean } : b)) }));
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

  const deleteBasket = useCallback((id: string) => {
    const cur = stateRef.current;
    const index = cur.baskets.findIndex(b => b.id === id);
    if (index < 0) return;
    const basket = cur.baskets[index];
    setState(s => {
      let rest = s.baskets.filter(b => b.id !== id);
      if (!rest.length) rest = [newBasket('הסל שלי')];
      return { baskets: rest, activeId: s.activeId === id ? rest[0].id : s.activeId };
    });
    showNotice({
      text: `הסל "${basket.name}" נמחק`,
      actionLabel: 'ביטול',
      onAction: () => { restoreBasket(basket, index); setNotice(null); },
    }, 6000);
  }, [showNotice]);

  const recordCompare = useCallback((id: string, snapshot: BasketSnapshot) => {
    setState(s => ({ ...s, baskets: s.baskets.map(b => (b.id === id ? { ...b, lastCompare: snapshot } : b)) }));
  }, []);

  const openCreate = useCallback(() => setPicker({ mode: 'create' }), []);
  const openMove = useCallback((items: LocalBasketItem[], fromId: string) => setPicker({ mode: 'move', items, fromId }), []);

  /** Moves `item.quantity` of an item between baskets, leaving the active basket alone. */
  const shift = useCallback((item: LocalBasketItem, fromId: string, toId: string) => {
    setState(s => ({
      ...s,
      baskets: s.baskets.map(b => {
        if (b.id === fromId) {
          return {
            ...b,
            items: b.items
              .map(i => (i.barcode === item.barcode ? { ...i, quantity: i.quantity - item.quantity } : i))
              .filter(i => i.quantity > 0),
          };
        }
        if (b.id === toId) {
          const existing = b.items.find(i => i.barcode === item.barcode);
          return {
            ...b,
            items: existing
              ? b.items.map(i => (i.barcode === item.barcode ? { ...i, quantity: i.quantity + item.quantity } : i))
              : [...b.items, item],
          };
        }
        return b;
      }),
    }));
  }, []);

  const moveTo = useCallback((moved: LocalBasketItem[], fromId: string, toId: string, toName: string) => {
    moved.forEach(item => shift(item, fromId, toId));
    showNotice({
      text: moved.length === 1 ? `הועבר ל"${toName}"` : `${moved.length} מוצרים הועברו ל"${toName}"`,
      actionLabel: 'ביטול',
      onAction: () => { moved.forEach(item => shift(item, toId, fromId)); setNotice(null); },
    });
  }, [shift, showNotice]);
  const closePicker = useCallback(() => setPicker(null), []);

  const pickBasket = useCallback((id: string) => {
    const p = picker;
    setPicker(null);
    const target = stateRef.current.baskets.find(b => b.id === id);
    if (!target || !p || p.mode === 'create') return;
    if (p.mode === 'move') moveTo(p.items, p.fromId, target.id, target.name);
    else addTo(target.id, p.item);
  }, [picker, addTo, moveTo]);

  const pickNew = useCallback((name: string) => {
    const p = picker;
    setPicker(null);
    if (p && p.mode === 'move') {
      // A new basket made for a move should not steal the active basket from the page being edited
      const id = uid();
      const label = name.trim() || 'סל חדש';
      setState(s => ({ ...s, baskets: [...s.baskets, { ...newBasket(label), id }] }));
      moveTo(p.items, p.fromId, id, label);
      return;
    }
    const id = createBasket(name);
    if (p && p.mode === 'add') addTo(id, p.item);
  }, [picker, createBasket, addTo, moveTo]);

  const active = state.baskets.find(b => b.id === state.activeId) ?? state.baskets[0];
  const totalItems = active.items.reduce((sum, i) => sum + i.quantity, 0);

  const value = useMemo<BasketContextValue>(() => ({
    baskets: state.baskets, activeId: active.id, active, items: active.items,
    addItem, removeItem, removeItems, updateQty, clearBasket, totalItems,
    setActive, createBasket, renameBasket, deleteBasket, recordCompare,
    notice, dismissNotice, picker, openCreate, openMove, closePicker, pickBasket, pickNew,
  }), [state.baskets, active, totalItems, addItem, removeItem, removeItems, updateQty, clearBasket,
       setActive, createBasket, renameBasket, deleteBasket, recordCompare,
       notice, dismissNotice, picker, openCreate, openMove, closePicker, pickBasket, pickNew]);

  return <BasketContext.Provider value={value}>{children}</BasketContext.Provider>;
}

export function useBasket(): BasketContextValue {
  const ctx = useContext(BasketContext);
  if (!ctx) throw new Error('useBasket must be used inside BasketProvider');
  return ctx;
}
