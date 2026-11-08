import { ErrorState } from '../components/ErrorState';
import { useState, useRef, useEffect, lazy, Suspense, Fragment } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShoppingBasket, Search, Minus, Plus, Trash2,
  ChevronDown, ChevronUp, TrendingUp,
  Truck, CheckCircle2, ExternalLink, Navigation, MapPin, ArrowLeftRight, Pencil, Check, MoreHorizontal, SlidersHorizontal, X, List, Map as MapIcon,
} from 'lucide-react';
import { compareBasket, fetchSubstitutes, fetchCities } from '../api/client';
import { StoreRow } from '../components/StoreRow';
import { money, safeHttpUrl } from '../lib/safe';
import { useDocumentTitle } from '../lib/useDocumentTitle';
import { EILAT_NOTE, eilatLast, googleMapsLink, isEilat, isMappable, isOnlineStore, storeAddress, storeSubtitle, wazeLink } from '../lib/store';
import { ProductImage } from '../components/ProductImage';
import { FilterSheet } from '../components/FilterSheet';
import { endsText } from '../lib/dealDays';
import { LocationPrompt } from '../components/LocationPrompt';
import { useCurrentCity, readMyCoords, type Coords } from '../lib/location';
import { useBasket } from '../context/BasketContext';
import { matchCity, onCityFilterChange, readCityFilter, readChainFilter, saveCityFilter, saveChainFilter } from '../lib/filters';
import { BasketSwitcher } from '../components/BasketSwitcher';
import { snapshotFrom, timeAgo } from '../lib/basketCompare';
import type { BasketCompareResponse, BasketSnapshot, BasketStoreTotal, StoreResponse, Substitute } from '../types';
import { track } from '../lib/track';

// The map library is large: it is fetched only when someone opens the map
const BasketMap = lazy(() => import('../components/BasketMap'));

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

function fmt(p: number | string) { return money(p); }

// Same navigation links as the product page's store rows (Waze and Google Maps both accept a free-text destination).
const navText = (store: StoreResponse) => ({ chain: store.chain.name, name: store.name, address: store.address, city: store.city });
const wazeUrl = (store: StoreResponse) => wazeLink(navText(store));
const googleMapsUrl = (store: StoreResponse) => googleMapsLink(navText(store));

/* ── Result card ─────────────────────────────────────────── */
function ResultCard({ store: row, rank, nextTotal, minTotal, totalItems, basketItems, fetchDetail }: {
  store: BasketStoreTotal; rank: number; nextTotal: number | null; minTotal: number; totalItems: number;
  /** The products of this comparison, to tell which ones this store does not sell */
  basketItems: { barcode: string; name: string }[];
  /** Asks for the item lines of one store (the list beside the map only has totals until a card is opened) */
  fetchDetail?: (storeId: number) => Promise<BasketStoreTotal | null>;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<BasketStoreTotal | null>(null);
  const [detailFailed, setDetailFailed] = useState(false);
  const needsDetail = !!fetchDetail && row.item_prices.length === 0 && row.items_found > 0;
  useEffect(() => {
    if (!open || !needsDetail || detail) return;
    let current = true;
    fetchDetail!(row.store.id).then(d => { if (current) { if (d) setDetail(d); else setDetailFailed(true); } })
      .catch(() => { if (current) setDetailFailed(true); });
    return () => { current = false; };
  }, [open]);   // eslint-disable-line react-hooks/exhaustive-deps
  const store = detail ?? row;
  const waitingForDetail = needsDetail && !detail;
  const missing = waitingForDetail ? [] : basketItems.filter(i => !store.item_prices.some(p => p.barcode === i.barcode));
  // Something like each missing product that this store does sell: asked for only when the card is opened
  const [subs, setSubs] = useState<Record<string, Substitute> | null>(null);
  useEffect(() => {
    if (!open || missing.length === 0 || subs) return;
    let current = true;
    fetchSubstitutes(store.store.id, missing.map(m => m.barcode))
      .then(r => { if (current) setSubs(r); })
      .catch(() => { if (current) setSubs({}); });      // a suggestion is a bonus: no message when it fails
    return () => { current = false; };
  }, [open, missing.length]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Only a store with the whole basket can be "the cheapest": a partial basket always looks cheap
  const isWinner  = rank === 0 && store.items_missing === 0;
  // How much cheaper this store is than the next one in the list (never against the dearest branch of all,
  // which would make the saving look bigger than it is).
  const lead      = nextTotal != null ? nextTotal - store.total_price : 0;
  const promoSavings = Number(store.savings ?? 0);

  return (
    <StoreRow
      chain={store.store.chain.name}
      name={store.store.chain.name}
      city={storeSubtitle({ chain: store.store.chain.name, name: store.store.name, address: store.store.address, city: store.store.city })}
      warning={[store.items_missing > 0 && `חסרים ${store.items_missing} מתוך ${totalItems} מוצרים · הסכום חלקי`, isEilat(store.store.city) && EILAT_NOTE].filter(Boolean).join(' · ') || undefined}
      price={store.total_price}
      isCheapest={isWinner}
      partial={store.items_missing > 0}
      diff={store.items_missing > 0 ? undefined : store.total_price - minTotal}
      open={open}
      onToggle={() => setOpen(v => !v)}
      banner={isWinner && lead > 0.01 ? (
        <div className="basket-result-savings savings-pop">
          <CheckCircle2 size={16} strokeWidth={2} color="var(--green-700)" />
          <span className="basket-result-savings-text">
            זול ב-<strong className="tabular">{fmt(lead)}</strong> מהסניף הבא
          </span>
        </div>
      ) : undefined}
    >
      {(() => {
        const addr = storeAddress({ chain: store.store.chain.name, name: store.store.name, address: store.store.address, city: store.store.city });
        return addr ? <div className="store-row-sub">כתובת: {addr}</div> : null;
      })()}
      <div className="store-row-actions">
        {!isOnlineStore({ chain: store.store.chain.name, name: store.store.name, address: store.store.address }) && (<>
        <a href={wazeUrl(store.store)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בוויז ל-${store.store.name}`}>
          <Navigation size={12} strokeWidth={2} />
          Waze
        </a>
        <a href={googleMapsUrl(store.store)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בגוגל מפות ל-${store.store.name}`}>
          <MapPin size={12} strokeWidth={2} />
          Maps
        </a>
        </>)}
        {safeHttpUrl(store.store.delivery_url) && (
          <a href={safeHttpUrl(store.store.delivery_url) as string} target="_blank" rel="noopener noreferrer">
            <Truck size={12} strokeWidth={2} />
            משלוח
            <ExternalLink size={10} strokeWidth={2} />
          </a>
        )}
      </div>

      <div className="basket-result-breakdown">
        {waitingForDetail && <div className="store-row-sub" style={{ padding: '10px 14px' }}>{detailFailed ? 'לא הצלחנו לטעון את הפירוט. נסו שוב.' : 'טוען פירוט...'}</div>}
        {store.item_prices.map((item, i) => (
          <div key={i} className="basket-breakdown-row">
            <div className="basket-breakdown-name" title={item.product_name}>
              {item.product_name}
              {item.quantity > 1 && (
                <span style={{ color: 'var(--ink-400)', marginInlineStart: 4 }}>×{item.quantity}</span>
              )}
              {item.promo && (
                <div className="basket-breakdown-promo">
                  מבצע: {item.promo.description}{item.promo.sets > 1 ? ` (×${item.promo.sets})` : ''}
                  {endsText(item.promo.ends_at, 7) && <span className="basket-breakdown-ends"> · {endsText(item.promo.ends_at, 7)}</span>}
                </div>
              )}
              {!item.promo && (store.promo_adjustments ?? []).some(a => a.barcodes.includes(item.barcode)) && (
                <div className="basket-breakdown-promo">במבצע משותף</div>
              )}
            </div>
            {item.missing
              ? <span className="basket-breakdown-missing">לא זמין</span>
              : <span className="basket-breakdown-line tabular">
                  {item.promo && item.regular_line_total != null && (
                    <s className="basket-breakdown-was">{fmt(item.regular_line_total)}</s>
                  )}
                  {fmt(item.line_total)}
                </span>
            }
          </div>
        ))}

        {missing.map(m => (
          <div key={`miss-${m.barcode}`} className="basket-breakdown-row basket-breakdown-lacking">
            <div className="basket-breakdown-name" title={m.name}>
              {m.name}
              {subs?.[m.barcode] && (
                <div className="basket-breakdown-sub">
                  בסניף הזה יש במקומו: {subs[m.barcode].name} · {fmt(subs[m.barcode].price)} (הצעה, לא כלולה בסכום)
                </div>
              )}
            </div>
            <span className="basket-breakdown-missing">לא זמין</span>
          </div>
        ))}

        {(store.promo_adjustments ?? []).map((a, i) => (
          <div key={`adj-${i}`} className="basket-breakdown-row basket-breakdown-adjustment">
            <div className="basket-breakdown-name" title={a.description}>
              <div className="basket-breakdown-promo">
                מבצע: {a.description}{a.sets > 1 ? ` (×${a.sets})` : ''}
                {endsText(a.ends_at, 7) && <span className="basket-breakdown-ends"> · {endsText(a.ends_at, 7)}</span>}
              </div>
            </div>
            <span className="basket-breakdown-line tabular">−{fmt(a.saving)}</span>
          </div>
        ))}
        {promoSavings > 0.005 && (
          <div className="basket-breakdown-row basket-breakdown-saving">
            <div className="basket-breakdown-name">הסכום כולל מבצעים</div>
            <span className="basket-breakdown-line tabular">חיסכון {fmt(promoSavings)}</span>
          </div>
        )}
        {store.promotions_known === false && (
          <div className="store-row-sub basket-no-promo">אין לנו נתוני מבצעים לסניף הזה, ייתכן שהמחיר בפועל נמוך יותר.</div>
        )}
        <div className="basket-breakdown-row"
          style={{ background: 'var(--surface-50)', borderTop: '2px solid var(--line)' }}>
          <div className="basket-breakdown-name" style={{ fontWeight: 700 }}>סה״כ</div>
          <span className="basket-breakdown-line tabular" style={{ fontSize: 17, fontWeight: 800 }}>
            {fmt(store.total_price)}
          </span>
        </div>
      </div>
    </StoreRow>
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
function SwipeRow({ onRemove, onClick, disabled, className, children }: {
  onRemove: () => void; onClick?: () => void; disabled?: boolean; className: string; children: React.ReactNode;
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
        onClick={onClick}
      >
        {children}
      </div>
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────── */
export function BasketPage() {
  const navigate = useNavigate();
  useDocumentTitle('הסל שלי | סלי');
  const { items, updateQty, removeItem, removeItems, clearBasket, activeId, active, recordCompare, openMove } = useBasket();
  const [results, setResults] = useState<BasketCompareResponse | null>(null);
  const requestId = useRef(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [city, setCity]       = useState(readCityFilter);
  const [chain, setChain]     = useState(readChainFilter);
  // How the previous comparison of this basket looked, to say what changed since then
  const [prevCompare, setPrevCompare] = useState<BasketSnapshot | null>(null);
  const [nowCompare, setNowCompare] = useState<BasketSnapshot | null>(null);
  // Switching baskets: forget the old results AND any comparison still in flight (its answer belongs to the other basket)
  useEffect(() => { requestId.current++; setLoading(false); setResults(null); setPrevCompare(null); setNowCompare(null); setError(null); }, [activeId]);
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
  // Linking list and map: the card under the pointer lights its pin; a pin picked on the map scrolls to its card
  const [mapBounds, setMapBounds] = useState<{ west: number; south: number; east: number; north: number } | null>(null);
  const [hoverId, setHoverId] = useState<number | null>(null);
  const [focusId, setFocusId] = useState<number | null>(null);
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

  // Products left out of this comparison only (the basket itself is not changed)
  const [skipped, setSkipped] = useState<string[]>([]);
  useEffect(() => { setSkipped([]); }, [activeId, items.length]);

  async function runCompare(filters: { city: string; chain: string }, skip: string[] = skipped) {
    const compareItems = items.filter(i => !skip.includes(i.barcode));
    if (!compareItems.length) return;
    const id = ++requestId.current;  // only the latest request may update the page
    setLoading(true); setError(null); setResults(null);
    try {
      const data = await compareBasket(compareItems.map(i => ({ barcode: i.barcode, quantity: i.quantity })), filters);
      if (id !== requestId.current) return;
      setResults(data);
      track('basket_compare', { value: items.length });
      const snap = skip.length === 0 ? snapshotFrom(data, items, filters) : null;   // a basket without some products is not the basket
      if (snap) {
        setPrevCompare(active.lastCompare ?? null);
        setNowCompare(snap);
        recordCompare(active.id, snap);
      }
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    } catch {
      if (id === requestId.current) setError('לא הצלחנו להשוות את הסל כרגע. נסו שוב בעוד רגע.');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  const handleCompare = () => void runCompare({ city, chain }, skipped);
  function compareWithout(barcodes: string[]) { setSkipped(barcodes); void runCompare({ city, chain }, barcodes); }
  // The totals on screen no longer match once a quantity changes: clear them (removing an item already does).
  function changeQty(barcode: string, quantity: number) { setResults(null); updateQty(barcode, quantity); }

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
  const [myCoords, setMyCoords] = useState<Coords | null>(() => readMyCoords());
  const { locate, request, pickCity, suggestedCity, locating, problem, dismiss } = useCurrentCity(onLocatedCity, setMyCoords);
  const [view, setView] = useState<'list' | 'map'>('list');
  // On a wide screen the list and the map sit side by side (the map is the main thing); the switch is for phones
  const [wide, setWide] = useState(() => window.matchMedia?.('(min-width: 1100px)').matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.('(min-width: 1100px)');
    if (!mq) return;
    const on = () => setWide(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  const mapActive = wide || view === 'map';
  // On a wide screen the results and the map come first: the basket's own items fold away until asked for
  const shownCount = wide && results ? 0 : COLLAPSED_COUNT;
  // The map shows every store, not just the 100 cheapest the list is cut to: fetched when the map is first opened
  // for these results. Once opened it stays mounted (hidden) so switching back and forth keeps zoom and selection.
  const [mapOpened, setMapOpened] = useState(false);
  // Branches that lack products look cheaper than they are: by default only complete baskets are compared
  const [onlyComplete, setOnlyComplete] = useState(true);
  const [mapData, setMapData] = useState<{ source: BasketCompareResponse; stores: BasketStoreTotal[] } | null>(null);
  useEffect(() => { if (mapActive) setMapOpened(true); }, [mapActive]);
  useEffect(() => {
    if (!mapActive || !results || mapData?.source === results) return;
    let stale = false;
    const done = (stores: BasketStoreTotal[]) => { if (!stale) setMapData({ source: results, stores }); };
    compareBasket(items.filter(i => !skipped.includes(i.barcode)).map(i => ({ barcode: i.barcode, quantity: i.quantity })), { city, chain }, true)
      .then(d => done(d.stores))
      .catch(() => done(results.stores));         // the map still works with the stores the list has
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapActive, results]);

  // The stores the list shows. On a narrow screen: the cheapest 100 of the comparison. Beside the map: the stores in
  // the map's view, cheapest first (complete baskets first, Eilat after the rest), the way the map's pins are.
  const mapReady = !!results && mapData?.source === results && mapBounds != null;
  const inView = wide && mapReady
    ? eilatLast(
        mapData!.stores
          .filter(s => isMappable(s) && s.store.latitude! >= mapBounds!.south && s.store.latitude! <= mapBounds!.north
            && s.store.longitude! >= mapBounds!.west && s.store.longitude! <= mapBounds!.east)
          .sort((a, b) => a.items_missing - b.items_missing || Number(a.total_price) - Number(b.total_price)),
        s => s.store.city, s => s.items_missing)
    : [];
  const pool = results ? (wide ? inView : results.stores) : [];
  const listLoading = !!results && wide && !mapReady;
  // Complete baskets only, unless none is complete or none is partial (then there is nothing to choose)
  const partialCount = pool.filter(s => s.items_missing > 0).length;
  const noCompleteStore = pool.length > 0 && partialCount === pool.length;
  const hasPartial = partialCount > 0 && !noCompleteStore;
  const filterComplete = onlyComplete && hasPartial;
  const shownStores = (filterComplete ? pool.filter(s => s.items_missing === 0) : pool).slice(0, 100);

  // A product most stores do not sell makes almost every basket partial: offer the comparison without it
  // With no complete basket at all, the rarest products are what is in the way, however common each one is alone
  const rareItems = results && items.filter(i => !skipped.includes(i.barcode)).length > 1
    ? (results.item_coverage ?? [])
        .filter(c => c.stores_total >= 10 && (noCompleteStore ? c.stores_with_item < c.stores_total : c.stores_with_item / c.stores_total <= 0.4))
        .sort((a, b) => a.stores_with_item / a.stores_total - b.stores_with_item / b.stores_total)
        .slice(0, 3)
    : [];
  const skippedNames = items.filter(i => skipped.includes(i.barcode)).map(i => i.name);

  // The winner's lead is measured against the next store that has as much of the basket as the winner.
  const nextStore = shownStores.length > 1
    ? shownStores.slice(1).find(s => s.items_missing === shownStores[0].items_missing)
    : undefined;
  const nextTotal = nextStore ? Number(nextStore.total_price) : null;
  const minTotal = shownStores.length > 0 ? shownStores[0].total_price : 0;
  const basketItems = items.filter(i => !skipped.includes(i.barcode)).map(i => ({ barcode: i.barcode, name: i.name }));
  const fetchDetail = (storeId: number) =>
    compareBasket(items.filter(i => !skipped.includes(i.barcode)).map(i => ({ barcode: i.barcode, quantity: i.quantity })), { city, chain }, false, [storeId])
      .then(d => d.stores[0] ?? null);
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
              הוסיפו משהו: חפשו מוצר והוסיפו לסל כדי להשוות מחירים
            </div>
            <button className="btn btn-primary btn-lg" onClick={() => navigate('/')}>
              <Search size={18} strokeWidth={2} />
              חפשו מוצרים
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
                        ניקוי כל הסל
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
            {(editing || showAllItems ? items : items.slice(0, shownCount)).map(item => (
              <SwipeRow
                key={item.barcode}
                className={`basket-item${editing ? ' editing' : ''}${selected.has(item.barcode) ? ' selected' : ''}`}
                disabled={editing}
                onRemove={() => { setResults(null); removeItem(item.barcode); }}
                onClick={editing ? () => toggleSelected(item.barcode) : undefined}
              >
                <div style={{ display: 'contents' }}>
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
                <span className="basket-item-pic"><ProductImage barcode={item.barcode} name={item.name} size={64} borderRadius={0} /></span>
                <div
                  className="basket-item-body"
                  style={{ cursor: 'pointer' }}
                  // While editing, a tap anywhere on the row selects it (the row handles that);
                  // outside editing it opens the product.
                  onClick={editing ? undefined : () => navigate(`/product/${item.barcode}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter') { if (editing) toggleSelected(item.barcode); else navigate(`/product/${item.barcode}`); } }}
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
                      onClick={() => item.quantity <= 1 ? removeItem(item.barcode) : changeQty(item.barcode, item.quantity - 1)}
                      aria-label={item.quantity <= 1 ? 'הסרה מהסל' : 'הפחתת כמות'}
                    >
                      {item.quantity <= 1
                        ? <Trash2 size={13} strokeWidth={2} color="var(--red-500)" />
                        : <Minus size={13} strokeWidth={2.5} />
                      }
                    </button>
                    <span className="qty-value">{item.quantity}</span>
                    <button
                      className="qty-btn"
                      onClick={() => changeQty(item.barcode, item.quantity + 1)}
                      aria-label="הגדלת כמות"
                    >
                      <Plus size={13} strokeWidth={2.5} />
                    </button>
                  </div>
                )}
                </div>
              </SwipeRow>
            ))}
            {!editing && items.length > shownCount && (
              <button className="basket-more" onClick={() => setShowAllItems(v => !v)} aria-expanded={showAllItems}>
                {showAllItems
                  ? <><ChevronUp size={15} strokeWidth={2} /> הציגו פחות</>
                  : <><ChevronDown size={15} strokeWidth={2} /> {shownCount === 0 ? `הציגו את ${items.length} המוצרים בסל` : `הציגו עוד ${items.length - shownCount} מוצרים`}</>}
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
          הוסיפו מוצר
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
                aria-label="ניקוי סינון"
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
        {error && <ErrorState text={error} onRetry={handleCompare} compact />}

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

            <div className={wide ? 'results-area' : undefined}>
            <div className="section-header" style={{ marginBottom: 16 }}>
              <div>
                <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TrendingUp size={20} strokeWidth={2} color="var(--green-600)" />
                  {wide
                    ? (listLoading ? 'טוען סניפים...' : `${pool.length} סניפים באזור שבמפה · ממוין מהזול ליקר`)
                    : <>{results.total_stores ?? results.stores.length} סניפים · ממוין מהזול ליקר{results.total_stores != null && results.total_stores > results.stores.length ? ` (מוצגים ${results.stores.length} הזולים)` : ''}</>}
                </div>
                <div className="section-subtitle">
                  עבור {results.total_items_requested} מוצרים בסל
                  {(city || chain) && <> · {[chain, city && `ב${city}`].filter(Boolean).join(' ')}</>}
                </div>
              </div>
            </div>

            {(skipped.length > 0 || noCompleteStore || rareItems.length > 0) && (
              <div className="partial-note" role="status">
                {skipped.length > 0 && (
                  <div>
                    ההשוואה הזו בלי: {skippedNames.join(', ')}.{' '}
                    <button className="link-btn" onClick={() => compareWithout([])}>החזירו לסל</button>
                  </div>
                )}
                {noCompleteStore && <div>אף סניף לא מחזיק את כל המוצרים בסל, והסכומים כאן חלקיים.</div>}
                {rareItems.length > 0 && <div className="partial-note-head">אפשר להשוות בלי מוצרים שחסרים בהרבה סניפים:</div>}
                {rareItems.map(c => (
                  <div key={c.barcode} className="partial-note-row">
                    <span><strong>{c.name}</strong> · ב-{c.stores_with_item} מתוך {c.stores_total} סניפים</span>
                    <button className="link-btn" onClick={() => compareWithout([...skipped, c.barcode])}>השוו בלעדיו</button>
                  </div>
                ))}
              </div>
            )}

            {!wide && results.stores.length > 0 && (
              <div className="view-toggle" role="group" aria-label="תצוגה" style={{ marginBottom: 14 }}>
                <button aria-pressed={view === 'list'} onClick={() => setView('list')}><List size={14} strokeWidth={2.2} />רשימה</button>
                <button aria-pressed={view === 'map'} onClick={() => setView('map')}><MapIcon size={14} strokeWidth={2.2} />מפה</button>
              </div>
            )}

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
                    הציגו את כל החנויות
                  </button>
                )}
              </div>
            )}

            {(mapActive || mapOpened) && results.stores.length > 0 && (
              <div className="results-map" style={{ display: mapActive ? 'block' : 'none' }}>
                {mapData?.source === results ? (
                  <Suspense fallback={<div className="skeleton" style={{ height: 380, borderRadius: 16, marginBottom: 40 }} />}>
                    <BasketMap stores={mapData.stores} myCoords={myCoords} onCoords={setMyCoords} visible={mapActive}
                      onlyComplete={onlyComplete} onOnlyCompleteChange={setOnlyComplete}
                      highlightId={hoverId} onBoundsChange={setMapBounds} onSelectStore={id => { setFocusId(id); if (id != null && wide) document.getElementById(`store-card-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }} />
                  </Suspense>
                ) : (
                  <div className="skeleton" style={{ height: 380, borderRadius: 16, marginBottom: 40 }} />
                )}
              </div>
            )}

            {hasPartial && (
              <button className={`partial-toggle${filterComplete ? ' active' : ''}`} aria-pressed={filterComplete}
                      style={{ display: mapActive && !wide ? 'none' : undefined }} onClick={() => setOnlyComplete(!filterComplete)}>
                {filterComplete ? `רק סניפים עם כל המוצרים · מוסתרים ${partialCount}` : 'הציגו גם סניפים שחסרים בהם מוצרים'}
              </button>
            )}

            <div style={{ display: mapActive && !wide ? 'none' : 'flex', flexDirection: 'column', gap: 12, paddingBottom: 40 }}>
              {shownStores.map((store, idx) => (
                <Fragment key={`${store.store.id}-${idx}`}>
                  {!filterComplete && !noCompleteStore && store.items_missing > 0 && (idx === 0 || shownStores[idx - 1].items_missing === 0) && (
                    <div className="partial-divider">סניפים שחסרים בהם מוצרים · לא להשוואה ישירה</div>
                  )}
                  <div id={`store-card-${store.store.id}`} className={`store-card-wrap${focusId === store.store.id ? ' card-focus' : ''}`}
                       onMouseEnter={wide ? () => setHoverId(store.store.id) : undefined}
                       onMouseLeave={wide ? () => setHoverId(null) : undefined}>
                  <ResultCard
                    store={store}
                    rank={idx}
                    nextTotal={nextTotal}
                    minTotal={minTotal}
                    totalItems={results.total_items_requested}
                    basketItems={basketItems}
                    fetchDetail={wide ? fetchDetail : undefined}
                  />
                  </div>
                </Fragment>
              ))}
            </div>
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
                  השוו מחירים
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
