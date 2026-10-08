import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShoppingBasket, Search, Minus, Plus, Trash2,
  ChevronDown, ChevronUp, TrendingUp, AlertCircle,
  Tag, Truck, CheckCircle2, ExternalLink, Navigation, MapPin, ArrowLeftRight, Pencil, Check, MoreHorizontal, SlidersHorizontal, X,
} from 'lucide-react';
import { compareBasket, fetchCities } from '../api/client';
import { ChainLogo } from '../components/ChainLogo';
import { ProductImage } from '../components/ProductImage';
import { FilterSheet } from '../components/FilterSheet';
import { LocationPrompt } from '../components/LocationPrompt';
import { useCurrentCity } from '../lib/location';
import { useBasket } from '../context/BasketContext';
import { matchCity, onCityFilterChange, readCityFilter, readChainFilter, saveCityFilter, saveChainFilter } from '../lib/filters';
import { BasketSwitcher } from '../components/BasketSwitcher';
import { snapshotFrom, timeAgo } from '../lib/basketCompare';
import type { BasketCompareResponse, BasketSnapshot, BasketStoreTotal } from '../types';

function CartPercentIcon() {
  // Shopping cart with a clear percent sign inside, drawn in currentColor so it follows
  // the button's own color (including on hover), unlike a pasted image.
  return (
    <svg width="26" height="26" viewBox="0 0 28 28" fill="none" aria-hidden
      stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      {/* handle */}
      <path d="M2 3 H5.5 L7 6.5" />
      {/* basket */}
      <path d="M7 6.5 H25 L22 15.5 H10.5 Z" />
      <line x1="7" y1="6.5" x2="10.5" y2="15.5" />
      {/* wheels */}
      <circle cx="12.5" cy="22.5" r="2" />
      <circle cx="20" cy="22.5" r="2" />
      {/* percent sign, clearly inside the basket */}
      <line x1="12.3" y1="13" x2="19.3" y2="8.5" />
      <circle cx="13" cy="8.8" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="18.7" cy="12.7" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  );
}

function fmt(p: number | string) { return `₪${Number(p).toFixed(2)}`; }

// Same navigation links as the product page's store rows — Waze and Google Maps
// both accept a free-text destination, so no store coordinates are needed.
function storeNavQuery(store: { name: string; address?: string; city?: string; chain: { name: string } }): string {
  return [store.name, store.address, store.city].filter(Boolean).join(', ') || store.chain.name;
}
function wazeUrl(store: Parameters<typeof storeNavQuery>[0]): string {
  return `https://waze.com/ul?q=${encodeURIComponent(storeNavQuery(store))}&navigate=yes`;
}
function googleMapsUrl(store: Parameters<typeof storeNavQuery>[0]): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(storeNavQuery(store))}`;
}

/* ── Result card ─────────────────────────────────────────── */
function ResultCard({ store, rank, maxTotal, minTotal }: {
  store: BasketStoreTotal; rank: number; maxTotal: number; minTotal: number;
}) {
  const [open, setOpen] = useState(false);
  const isWinner  = rank === 0;
  const savings   = maxTotal - store.total_price;
  const savingsPct = maxTotal > 0 ? Math.round((savings / maxTotal) * 100) : 0;
  const diff = store.total_price - minTotal;

  return (
    <div className={`basket-result-card${isWinner ? ' winner' : ''}`}>

      {/* Winner savings banner */}
      {isWinner && savings > 0.01 && (
        <div className="basket-result-savings savings-pop">
          <CheckCircle2 size={16} strokeWidth={2} color="var(--green-700)" />
          <span className="basket-result-savings-text">
            חסכת{' '}
            <strong className="tabular">{fmt(savings)}</strong>
            {savingsPct > 0 && <span style={{ fontWeight: 400, opacity: 0.8 }}> ({savingsPct}%)</span>}
            {' '}בהשוואה לרשת היקרה ביותר
          </span>
        </div>
      )}

      {/* The whole header toggles the details: logo, store, total — nothing else competes */}
      <button className="basket-result-header basket-result-head-btn" onClick={() => setOpen(v => !v)} aria-expanded={open}>
        <ChainLogo name={store.store.chain.name} size={52} />

        <div className="basket-result-chain">
          <div className="basket-result-chain-name">{store.store.chain.name}</div>
          <div className="basket-result-store-info">
            {[store.store.name, store.store.city].filter(Boolean).join(' · ')}
          </div>
          {isWinner && (
            <span className="badge badge-cheapest" style={{ display: 'inline-flex', alignItems: 'center', gap: 3, marginTop: 4 }}>
              <Tag size={10} strokeWidth={2.5} />
              הכי זול
            </span>
          )}
          {store.items_missing > 0 && (
            <div className="basket-result-missing">
              <AlertCircle size={12} strokeWidth={2} />
              חסרים {store.items_missing} מוצרים
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <div className="basket-result-total tabular">{fmt(store.total_price)}</div>
          {!isWinner && diff > 0.01 && (
            <span className="compare-row-diff tabular">+{fmt(diff)}</span>
          )}
          {open ? <ChevronUp size={16} strokeWidth={2} color="var(--ink-400)" /> : <ChevronDown size={16} strokeWidth={2} color="var(--ink-400)" />}
        </div>
      </button>

      {open && (
        <>
          <div className="basket-result-actions">
            <a href={wazeUrl(store.store)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בוויז ל-${store.store.name}`}>
              <Navigation size={12} strokeWidth={2} />
              Waze
            </a>
            <a href={googleMapsUrl(store.store)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בגוגל מפות ל-${store.store.name}`}>
              <MapPin size={12} strokeWidth={2} />
              Maps
            </a>
            {store.store.delivery_url && (
              <a href={store.store.delivery_url} target="_blank" rel="noopener noreferrer" className="compare-row-delivery">
                <Truck size={12} strokeWidth={2} />
                משלוח
                <ExternalLink size={9} strokeWidth={2} />
              </a>
            )}
          </div>

          <div className="basket-result-breakdown">
            {store.item_prices.map((item, i) => (
              <div key={i} className="basket-breakdown-row">
                <div className="basket-breakdown-name" title={item.product_name}>
                  {item.product_name}
                  {item.quantity > 1 && (
                    <span style={{ color: 'var(--ink-400)', marginInlineStart: 4 }}>×{item.quantity}</span>
                  )}
                </div>
                {item.missing
                  ? <span className="basket-breakdown-missing">לא זמין</span>
                  : <span className="basket-breakdown-line tabular">{fmt(item.line_total)}</span>
                }
              </div>
            ))}

            <div className="basket-breakdown-row"
              style={{ background: 'var(--surface-50)', borderTop: '2px solid var(--line)' }}>
              <div className="basket-breakdown-name" style={{ fontWeight: 700 }}>סה״כ</div>
              <span className="basket-breakdown-line tabular" style={{ fontSize: 17, fontWeight: 800 }}>
                {fmt(store.total_price)}
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/** "Last time you looked, it was X — now it is Y" for the same basket and filters. */
function CompareDelta({ prev, now }: { prev: BasketSnapshot | null; now: BasketSnapshot }) {
  if (!prev) return <div className="compare-delta">זו ההשוואה הראשונה לסל הזה. בפעם הבאה נראה לך מה השתנה.</div>;
  const when = timeAgo(prev.at);
  if (prev.sig !== now.sig) {
    return <div className="compare-delta">בפעם הקודמת ({when}) הסל היה שונה: {fmt(prev.total)}. הוספת או הסרת מוצרים, אז אין השוואה ישירה.</div>;
  }
  if (prev.filterKey !== now.filterKey) {
    return <div className="compare-delta">בפעם הקודמת ({when}) סיננת אחרת, אז אין השוואה ישירה.</div>;
  }
  const diff = now.total - prev.total;
  if (Math.abs(diff) < 0.005) {
    return <div className="compare-delta">מאז {when} המחיר לא השתנה: <strong>{fmt(now.total)}</strong></div>;
  }
  const down = diff < 0;
  return (
    <div className="compare-delta">
      <span>
        בפעם הקודמת ({when}) הסל היה {fmt(prev.total)}, עכשיו <strong>{fmt(now.total)}</strong>
        {' '}— <strong className={down ? 'down' : 'up'}>{down ? 'ירד' : 'עלה'} ב-{fmt(Math.abs(diff))}</strong>
      </span>
    </div>
  );
}

/** Drag a row sideways far enough and it is removed (an undo notice follows). */
function SwipeRow({ onRemove, disabled, className, children }: {
  onRemove: () => void; disabled?: boolean; className: string; children: React.ReactNode;
}) {
  const [dx, setDx] = useState(0);
  const start = useRef<{ x: number; y: number; id: number } | null>(null);
  const dragging = useRef(false);
  const THRESHOLD = 90;

  function down(e: React.PointerEvent) {
    if (disabled || (e.target as HTMLElement).closest('button, input, a')) return;
    start.current = { x: e.clientX, y: e.clientY, id: e.pointerId };
    dragging.current = false;
  }
  function move(e: React.PointerEvent) {
    const st = start.current;
    if (!st) return;
    const mx = e.clientX - st.x;
    if (!dragging.current) {
      if (Math.abs(mx) < 8 || Math.abs(mx) < Math.abs(e.clientY - st.y)) return;  // vertical scroll wins
      dragging.current = true;
      (e.currentTarget as HTMLElement).setPointerCapture(st.id);
    }
    setDx(mx);
  }
  function up() {
    const wasDragging = dragging.current;
    start.current = null;
    dragging.current = false;
    if (wasDragging && Math.abs(dx) >= THRESHOLD) { onRemove(); }
    setDx(0);
  }

  const progress = Math.min(1, Math.abs(dx) / THRESHOLD);
  return (
    <div className="swipe-row">
      <div className="swipe-row-bg" style={{ opacity: progress }} aria-hidden>
        <Trash2 size={18} strokeWidth={2} />
      </div>
      <div
        className={className}
        style={{ transform: `translateX(${dx}px)`, transition: dx === 0 ? 'transform 0.2s' : 'none', touchAction: 'pan-y' }}
        onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
      >
        {children}
      </div>
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────── */
export function BasketPage() {
  const navigate = useNavigate();
  const { items, updateQty, removeItem, removeItems, clearBasket, activeId, active, recordCompare, openMove } = useBasket();
  const [results, setResults] = useState<BasketCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [city, setCity]       = useState(readCityFilter);
  const [chain, setChain]     = useState(readChainFilter);
  // How the previous comparison of this basket looked, to say what changed since then
  const [prevCompare, setPrevCompare] = useState<BasketSnapshot | null>(null);
  const [nowCompare, setNowCompare] = useState<BasketSnapshot | null>(null);
  useEffect(() => { setResults(null); setPrevCompare(null); setNowCompare(null); setError(null); }, [activeId]);
  // Edit mode: pick several items and move or delete them in one go
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => { setEditing(false); setSelected(new Set()); }, [activeId]);
  useEffect(() => {
    // Drop selections whose item has left this basket (moved or deleted); finish editing once nothing is left selected
    setSelected(prev => {
      const next = new Set([...prev].filter(b => items.some(i => i.barcode === b)));
      if (next.size === prev.size) return prev;
      if (next.size === 0) setEditing(false);
      return next;
    });
  }, [items]);
  function toggleSelected(barcode: string) {
    setSelected(prev => { const n = new Set(prev); if (n.has(barcode)) n.delete(barcode); else n.add(barcode); return n; });
  }
  // Long baskets show the first few items; the rest is one tap away (editing always shows all)
  const COLLAPSED_COUNT = 5;
  const [filterOpen, setFilterOpen] = useState(false);
  const [cities, setCities] = useState<string[]>([]);
  useEffect(() => { fetchCities().then(setCities).catch(() => {}); }, []);
  const [showAllItems, setShowAllItems] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    if (!menuOpen) return;
    const close = () => setMenuOpen(false);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [menuOpen]);
  useEffect(() => { setShowAllItems(false); }, [activeId]);
  const allSelected = items.length > 0 && selected.size === items.length;
  const resultsRef = useRef<HTMLDivElement>(null);
  const requestId  = useRef(0);

  async function runCompare(filters: { city: string; chain: string }) {
    if (!items.length) return;
    const id = ++requestId.current;  // only the latest request may update the page
    setLoading(true); setError(null); setResults(null);
    try {
      const data = await compareBasket(items.map(i => ({ barcode: i.barcode, quantity: i.quantity })), filters);
      if (id !== requestId.current) return;
      setResults(data);
      const snap = snapshotFrom(data, items, filters);
      if (snap) {
        setPrevCompare(active.lastCompare ?? null);
        setNowCompare(snap);
        recordCompare(active.id, snap);
      }
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    } catch {
      if (id === requestId.current) setError('לא הצלחנו להשוות. בדוק שהשרת פעיל ונסה שוב.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  const handleCompare = () => void runCompare({ city, chain });

  // A filter change re-runs a comparison that is already on screen
  function changeCity(next: string) {
    setCity(next); saveCityFilter(next);
    if (results || loading) void runCompare({ city: next, chain });
  }
  useEffect(() => onCityFilterChange(changeCity));  // header chip; resubscribes so it sees fresh state

  function changeChain(next: string) {
    setChain(next); saveChainFilter(next);
    if (results || loading) void runCompare({ city, chain: next });
  }

  const onLocatedCity = (found: string) => changeCity(matchCity(found, cities));
  const { locate, request, pickCity, suggestedCity, locating, problem, dismiss } = useCurrentCity(onLocatedCity);

  const completeStores = results ? results.stores.filter(s => s.items_missing === 0) : [];
  const maxTotal = completeStores.length >= 2
    ? Math.max(...completeStores.map(s => s.total_price))
    : results && results.stores.length ? Math.max(...results.stores.map(s => s.total_price)) : 0;
  const minTotal = results && results.stores.length > 0 ? results.stores[0].total_price : 0;
  const totalItems = items.reduce((s, i) => s + i.quantity, 0);

  /* Empty state */
  if (!items.length && !results) {
    return (
      <div className="page-wrapper">
        <div className="container">
          <BasketSwitcher />
          <div className="empty-state" style={{ paddingTop: 32 }}>
            <div className="empty-state-icon">
              <ShoppingBasket size={32} strokeWidth={1.5} />
            </div>
            <div className="empty-state-title">הסל שלך ריק</div>
            <div className="empty-state-desc">
              תוסיף משהו — חפש מוצר והוסף לסל כדי להשוות מחירים
            </div>
            <button className="btn btn-primary btn-lg" onClick={() => navigate('/')}>
              <Search size={18} strokeWidth={2} />
              חפש מוצרים
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page-wrapper">
      {/* Room for the sticky compare bar so the last item / result is never hidden under it */}
      <div className="container" style={{ paddingBottom: items.length > 0 ? 96 : 0 }}>

        {/* Header */}
        <div className="section-header" style={{ marginBottom: 20 }}>
          <div>
            <BasketSwitcher />
            <div className="section-subtitle">
              {items.length} מוצר{items.length !== 1 ? 'ים' : ''} · {totalItems} יח׳ בסך הכל
            </div>
          </div>
          {items.length > 0 && (
            <div style={{ display: 'flex', gap: 4 }}>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => { setEditing(e => !e); setSelected(new Set()); }}
              >
                {editing ? <Check size={15} strokeWidth={2} /> : <Pencil size={15} strokeWidth={1.8} />}
                {editing ? 'סיום' : 'עריכה'}
              </button>
              {!editing && (
                <div style={{ position: 'relative' }}>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={e => { e.stopPropagation(); setMenuOpen(v => !v); }}
                    aria-label="עוד פעולות"
                    aria-expanded={menuOpen}
                  >
                    <MoreHorizontal size={18} strokeWidth={2} />
                  </button>
                  {menuOpen && (
                    <div className="basket-menu" role="menu">
                      <button role="menuitem" onClick={() => { setResults(null); clearBasket(); setMenuOpen(false); }}>
                        <Trash2 size={15} strokeWidth={1.8} />
                        נקה את כל הסל
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Item list */}
        {items.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
            {(editing || showAllItems ? items : items.slice(0, COLLAPSED_COUNT)).map(item => (
              <SwipeRow
                key={item.barcode}
                className={`basket-item${editing ? ' editing' : ''}${selected.has(item.barcode) ? ' selected' : ''}`}
                disabled={editing}
                onRemove={() => { setResults(null); removeItem(item.barcode); }}
              >
                <div style={{ display: 'contents' }} onClick={editing ? () => toggleSelected(item.barcode) : undefined}>
                {editing && (
                  <input
                    type="checkbox"
                    className="basket-check"
                    checked={selected.has(item.barcode)}
                    onChange={() => toggleSelected(item.barcode)}
                    onClick={e => e.stopPropagation()}
                    aria-label={`בחירת ${item.name}`}
                  />
                )}
                <ProductImage barcode={item.barcode} name={item.name} size={48} />
                <div
                  className="basket-item-body"
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/product/${item.barcode}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => e.key === 'Enter' && navigate(`/product/${item.barcode}`)}
                >
                  <div className="basket-item-name">{item.name}</div>

                  <div className="basket-item-meta">
                    {[item.brand, item.unit].filter(Boolean).join(' · ')}
                  </div>
                </div>
                {!editing && (
                  <div className="basket-item-controls">
                    <button
                      className="qty-btn"
                      onClick={() => item.quantity <= 1 ? removeItem(item.barcode) : updateQty(item.barcode, item.quantity - 1)}
                      aria-label={item.quantity <= 1 ? 'הסר מהסל' : 'הפחת כמות'}
                    >
                      {item.quantity <= 1
                        ? <Trash2 size={13} strokeWidth={2} color="var(--red-500)" />
                        : <Minus size={13} strokeWidth={2.5} />
                      }
                    </button>
                    <span className="qty-value">{item.quantity}</span>
                    <button
                      className="qty-btn"
                      onClick={() => updateQty(item.barcode, item.quantity + 1)}
                      aria-label="הגדל כמות"
                    >
                      <Plus size={13} strokeWidth={2.5} />
                    </button>
                  </div>
                )}
                </div>
              </SwipeRow>
            ))}
            {!editing && items.length > COLLAPSED_COUNT && (
              <button className="basket-more" onClick={() => setShowAllItems(v => !v)} aria-expanded={showAllItems}>
                {showAllItems
                  ? <><ChevronUp size={15} strokeWidth={2} /> הצג פחות</>
                  : <><ChevronDown size={15} strokeWidth={2} /> הצג עוד {items.length - COLLAPSED_COUNT} מוצרים</>}
              </button>
            )}
          </div>
        )}

        {editing && (
          <div className="edit-bar" role="toolbar" aria-label="פעולות על מוצרים נבחרים">
            <label className="edit-bar-all">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={() => setSelected(allSelected ? new Set() : new Set(items.map(i => i.barcode)))}
              />
              הכל
            </label>
            <button
              className="btn btn-primary btn-sm"
              disabled={selected.size === 0}
              onClick={() => openMove(items.filter(i => selected.has(i.barcode)), activeId)}
            >
              <ArrowLeftRight size={15} strokeWidth={2} />
              העברה ({selected.size})
            </button>
            <button
              className="btn btn-secondary btn-sm"
              style={{ color: 'var(--red-500)' }}
              disabled={selected.size === 0}
              onClick={() => { setResults(null); removeItems([...selected]); }}
            >
              <Trash2 size={15} strokeWidth={1.8} />
              מחיקה ({selected.size})
            </button>
          </div>
        )}

        {/* Add more — a quiet row, so it does not compete with the compare action */}
        <button className="basket-add-more" onClick={() => navigate('/')}>
          <Plus size={16} strokeWidth={2.5} />
          הוסף מוצר
        </button>

        {/* One chip for city / chain; the comparison only covers what is chosen here */}
        {items.length > 0 && (
          <div className="filter-bar">
            <button
              className={`filter-chip${(city || chain) ? ' active' : ''}`}
              onClick={() => setFilterOpen(true)}
              aria-label="סינון חנויות"
            >
              <SlidersHorizontal size={15} strokeWidth={2} />
              {(city || chain) ? [city, chain].filter(Boolean).join(' · ') : 'סינון לפי עיר או רשת'}
              <ChevronDown size={13} strokeWidth={2.5} style={{ opacity: 0.6 }} />
            </button>
            {(city || chain) && (
              <button
                className="filter-chip-clear"
                onClick={() => { changeCity(''); changeChain(''); }}
                aria-label="נקי סינון"
              >
                <X size={15} strokeWidth={2.5} />
              </button>
            )}
          </div>
        )}

        {filterOpen && (
          <FilterSheet
            city={city}
            cities={cities}
            chain={chain}
            locating={locating}
            onCity={changeCity}
            onChain={changeChain}
            onLocate={locate}
            onClose={() => setFilterOpen(false)}
          />
        )}
        <LocationPrompt problem={problem} onRetry={locate} onConfirm={request} onPickCity={pickCity} suggestedCity={suggestedCity} onClose={dismiss} />

        {/* Error */}
        {error && (
          <div style={{ background: 'var(--red-100)', color: 'var(--red-600)', borderRadius: 'var(--r-lg)', padding: '12px 16px', fontSize: 14, marginBottom: 16 }}>
            {error}
          </div>
        )}

        {/* Loading skeletons */}
        {loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="card" style={{ padding: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div className="skeleton" style={{ width: 52, height: 52, borderRadius: 10 }} />
                  <div style={{ flex: 1 }}>
                    <div className="skeleton" style={{ height: 16, width: '50%', marginBottom: 8 }} />
                    <div className="skeleton" style={{ height: 13, width: '35%' }} />
                  </div>
                  <div className="skeleton" style={{ height: 28, width: 76 }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Results */}
        {results && !loading && (
          <>
            <div className="section-divider" ref={resultsRef}>תוצאות ההשוואה</div>

            {nowCompare && <CompareDelta prev={prevCompare} now={nowCompare} />}

            <div className="section-header" style={{ marginBottom: 16 }}>
              <div>
                <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TrendingUp size={20} strokeWidth={2} color="var(--green-600)" />
                  {results.stores.length} סניפים · ממוין מהזול ליקר
                </div>
                <div className="section-subtitle">
                  עבור {results.total_items_requested} מוצרים בסל
                  {(city || chain) && <> · {[chain, city && `ב${city}`].filter(Boolean).join(' ')}</>}
                </div>
              </div>
            </div>

            {results.stores.length === 0 && (
              <div className="empty-state" style={{ padding: '32px 0' }}>
                <div className="empty-state-title">
                  {city || chain ? `לא נמצאו חנויות ${[chain, city && `ב${city}`].filter(Boolean).join(' ')} עם המוצרים בסל` : 'לא נמצאו חנויות עם המוצרים בסל'}
                </div>
                {(city || chain) && (
                  <button className="btn btn-secondary btn-sm" onClick={() => {
                    setCity(''); setChain(''); saveCityFilter(''); saveChainFilter('');
                    void runCompare({ city: '', chain: '' });
                  }}>
                    הצג את כל החנויות
                  </button>
                )}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingBottom: 40 }}>
              {results.stores.map((store, idx) => (
                <ResultCard
                  key={`${store.store.id}-${idx}`}
                  store={store}
                  rank={idx}
                  maxTotal={maxTotal}
                  minTotal={minTotal}
                />
              ))}
            </div>
          </>
        )}
      </div>

      {/* Sticky compare bar: the page's main action stays reachable however long the list is */}
      {items.length > 0 && (
        <div className="add-to-basket-bar">
          <button
            className="btn btn-primary btn-compare btn-lg btn-full"
            onClick={handleCompare}
            disabled={loading}
          >
            {loading
              ? 'משווה מחירים...'
              : <>
                  <CartPercentIcon />
                  השווה מחירים
                  <span className="compare-bar-count">
                    {items.length === totalItems
                      ? `${totalItems} מוצרים`
                      : `${items.length} מוצרים · ${totalItems} יח׳`}
                  </span>
                </>
            }
          </button>
        </div>
      )}
    </div>
  );
}
