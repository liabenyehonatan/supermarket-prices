import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search, X, ChevronLeft, Barcode,
  MapPin, Plus, Check,
} from 'lucide-react';

function SearchProductIcon() {
  // Reference illustration: magnifying glass with an apple
  return <img src="/icons/search-apple.png" alt="" aria-hidden style={{ height: 56, width: 'auto', maxWidth: 'none' }} />;
}

function CompareTrendIcon() {
  // Thin line arrow trending up, drawn to match the line-art icons beside it
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden
      stroke="#4D6B39" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 37 L17 26 L25 32 L41 16" />
      <path d="M31 16 L41 16 L41 26" />
    </svg>
  );
}

function BuildBasketIcon() {
  // Reference illustration: hand dropping a carton into a basket with a plant
  return <img src="/icons/basket-plant.png" alt="" aria-hidden style={{ height: 56, width: 'auto', maxWidth: 'none' }} />;
}

import { searchProducts, cheapestPricesBatch } from '../api/client';
import { ProductImage } from '../components/ProductImage';
import { HeroBanner } from '../components/HeroBanner';
import { ChainCarousel } from '../components/ChainCarousel';
import { useBasket } from '../context/BasketContext';
import type { Product } from '../types';
import { cleanBrand, extractProductDisplay } from '../lib/utils';
import { timeAgo } from '../lib/basketCompare';
import { FEATURED_CHAINS, readChainFilter, saveChainFilter } from '../lib/filters';

/* ── constants ────────────────────────────────────────────── */
const PAGE_SIZE = 20;

/* ── search snapshot: going back from a product returns to the same results and scroll position ── */
const SNAPSHOT_KEY = 'sali_search_snapshot';
interface SearchSnapshot {
  q: string;
  results: Product[];
  hasMore: boolean;
  cheapest: Record<string, number>;
  scrollY: number;
}
function readSnapshot(q: string): SearchSnapshot | null {
  try {
    const raw = sessionStorage.getItem(SNAPSHOT_KEY);
    if (!raw) return null;
    const snap = JSON.parse(raw) as SearchSnapshot;
    return snap.q === q ? snap : null;
  } catch {
    return null;
  }
}
function writeSnapshot(snap: SearchSnapshot) {
  try {
    sessionStorage.setItem(SNAPSHOT_KEY, JSON.stringify(snap));
  } catch {
    // storage full or blocked — going back just reloads the results
  }
}
const POPULAR: { label: string; q: string }[] = [
  { label: 'חלב 3%', q: 'חלב' },
  { label: 'לחם אחיד', q: 'לחם' },
  { label: 'ביצים', q: 'ביצים' },
  { label: 'קוטג׳', q: 'קוטג' },
  { label: 'אורז בסמטי', q: 'אורז' },
  { label: 'שמן זית', q: 'שמן זית' },
  { label: 'יוגורט', q: 'יוגורט' },
  { label: 'גבינה צהובה', q: 'גבינה' },
];

/* ── helpers ──────────────────────────────────────────────── */
function fmt(p: number | string) {
  return `₪${Number(p).toFixed(2)}`;
}

/* ── sub-components ───────────────────────────────────────── */
function QuickAddButton({ product, small }: { product: Product; small?: boolean }) {
  const { addItem } = useBasket();
  const [added, setAdded] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleAdd(e: React.SyntheticEvent) {
    e.preventDefault();
    e.stopPropagation();
    addItem({
      barcode: product.barcode,
      quantity: 1,
      name: product.name,
      brand: product.brand,
      unit: product.unit_of_measure,
    });
    setAdded(true);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setAdded(false), 1400);
  }

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  return (
    <button
      type="button"
      className={`quick-add-btn${small ? ' small' : ''}${added ? ' added' : ''}`}
      onMouseDown={handleAdd}
      aria-label={`הוסף ${product.name} לסל`}
      title="הוסף לסל"
    >
      {added ? <Check size={small ? 14 : 16} strokeWidth={2.5} /> : <Plus size={small ? 14 : 16} strokeWidth={2.5} />}
    </button>
  );
}

/* ── main component ───────────────────────────────────────── */
export function SearchPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialSnap = useRef<SearchSnapshot | null>(readSnapshot(searchParams.get('q') ?? ''));
  // "How it works" shows once; afterwards it is only a small link away
  const [showHow, setShowHow] = useState(() => {
    try { return localStorage.getItem('sali_seen_how') !== '1'; } catch { return true; }
  });
  function closeHow() {
    setShowHow(false);
    try { localStorage.setItem('sali_seen_how', '1'); } catch { /* storage blocked — card returns next visit */ }
  }
  const { baskets, activeId, setActive, openCreate } = useBasket();
  // With one basket the card only appears once it has items; with several they are all listed
  const shownBaskets = baskets.length > 1 ? baskets : baskets.filter(b => b.items.length > 0);
  const [query, setQuery]     = useState(searchParams.get('q') ?? '');
  const [results, setResults] = useState<Product[]>(() => initialSnap.current?.results ?? []);
  const [hasMore, setHasMore] = useState(() => initialSnap.current?.hasMore ?? false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [cheapest, setCheapest] = useState<Record<string, number>>(() => initialSnap.current?.cheapest ?? {});
  // City and chain filters also live in the URL (?city= / ?supermarket=) so a
  // refresh or a shared link keeps them; sessionStorage carries them across pages.
  const [chainFilter, setChainFilter] = useState<string>(() => searchParams.get('supermarket') ?? readChainFilter());
  const [focused, setFocused] = useState(false);
  const inputRef  = useRef<HTMLInputElement>(null);
  const debounce  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownMax, setDropdownMax] = useState(360);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); setHasMore(false); setError(null); return; }
    setLoading(true); setError(null);
    try {
      const page = await searchProducts(q.trim(), PAGE_SIZE, 0);
      setResults(page);
      setHasMore(page.length === PAGE_SIZE);
    } catch {
      setError('לא הצלחנו לטעון. בדוק שהשרת פעיל ונסה שוב.');
      setResults([]);
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, []);

  async function loadMore() {
    if (!query.trim() || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await searchProducts(query.trim(), PAGE_SIZE, results.length);
      setResults(prev => [...prev, ...page]);
      setHasMore(page.length === PAGE_SIZE);
    } catch {
      setError('לא הצלחנו לטעון עוד תוצאות. נסה שוב.');
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    const q = searchParams.get('q') ?? '';
    setQuery(q);
    setChainFilter(searchParams.get('supermarket') ?? sessionStorage.getItem('chainFilter') ?? '');
    const restore = initialSnap.current;
    if (restore && restore.q === q) {
      // Came back from a product page: the results are already here, just restore the scroll
      if (restore.scrollY > 0) setTimeout(() => window.scrollTo(0, restore.scrollY), 0);
      return;
    }
    if (q) void doSearch(q);
  }, [searchParams, doSearch]);

  // Save the current results for the URL's query, so "back" can restore them
  useEffect(() => {
    const q = (searchParams.get('q') ?? '').trim();
    if (!q || loading || !results.length) return;
    writeSnapshot({ q, results, hasMore, cheapest, scrollY: readSnapshot(q)?.scrollY ?? 0 });
  }, [searchParams, results, hasMore, cheapest, loading]);

  // Track the scroll position for the current query (throttled)
  useEffect(() => {
    const q = (searchParams.get('q') ?? '').trim();
    // Remember the last position the user scrolled to. Read it from the scroll events,
    // not at unmount: the site scrolls smoothly, so the value at unmount is mid-animation.
    let lastY = window.scrollY;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const saveScroll = (y: number) => {
      const snap = readSnapshot(q);
      if (snap) writeSnapshot({ ...snap, scrollY: y });
    };
    const onScroll = () => {
      lastY = window.scrollY;
      if (timer) return;
      timer = setTimeout(() => { timer = null; saveScroll(lastY); }, 200);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (timer) clearTimeout(timer);
      saveScroll(lastY);
    };
  }, [searchParams]);

  // Fetch the cheapest price for every visible result in a single request,
  // instead of one /compare call per product.
  useEffect(() => {
    const missing = results.filter(p => cheapest[p.barcode] == null).map(p => p.barcode);
    if (!missing.length) return;
    void (async () => {
      try {
        const map = await cheapestPricesBatch(missing);
        setCheapest(prev => ({ ...prev, ...map }));
      } catch { /* ignore — results just keep their skeleton price */ }
    })();
  }, [results]);

  function handleInput(val: string) {
    setQuery(val);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setSearchParams(val.trim() ? { q: val.trim() } : {}, { replace: true });
    }, 320);
  }

  function selectChain(name: string) {
    const next = chainFilter === name ? '' : name;
    setChainFilter(next);
    saveChainFilter(next);
    setSearchParams(prev => {
      const params = new URLSearchParams(prev);
      if (next) params.set('supermarket', next);
      else params.delete('supermarket');
      return params;
    }, { replace: true });
  }

  // The dropdown is a preview; closing it reveals the full, scrollable results list
  function showAllResults() {
    setFocused(false);
    inputRef.current?.blur();
  }

  function clearSearch() {
    setQuery(''); setResults([]); setHasMore(false); setError(null);
    setSearchParams({}, { replace: true });
    inputRef.current?.focus();
  }

  function startSearch(q: string) {
    setQuery(q);
    setSearchParams({ q: q.trim() }, { replace: true });
  }

  const hasQuery = query.trim().length > 0;

  // Sort: names starting with query come first
  const sortedResults = [...results].sort((a, b) => {
    const q = query.trim().toLowerCase();
    const aS = a.name.toLowerCase().startsWith(q) ? 0 : 1;
    const bS = b.name.toLowerCase().startsWith(q) ? 0 : 1;
    return aS - bS;
  });

  const showDropdown = focused && hasQuery && sortedResults.length > 0;
  const showDropdownSkeleton = focused && hasQuery && loading && sortedResults.length === 0;

  // Size the dropdown so it always ends above the bottom nav bar
  useEffect(() => {
    if (!showDropdown) return;
    const fit = () => {
      const el = dropdownRef.current;
      if (!el) return;
      const nav = document.querySelector('.bottom-nav');
      const navTop = nav && getComputedStyle(nav).display !== 'none'
        ? nav.getBoundingClientRect().top
        : window.innerHeight;
      setDropdownMax(Math.max(200, navTop - el.getBoundingClientRect().top - 12));
    };
    fit();
    window.addEventListener('resize', fit);
    window.addEventListener('scroll', fit, { passive: true });
    return () => {
      window.removeEventListener('resize', fit);
      window.removeEventListener('scroll', fit);
    };
  }, [showDropdown]);

  /* ── render ─────────────────────────────────────────────── */
  return (
    <div className="page-wrapper">
      <div className="container">

        {/* ── Hero ─────────────────────────────────────────── */}
        {!hasQuery && (
          <div className="hero-section">
            <HeroBanner title="השוואת מחירי סופרמרקט" />
            <p className="hero-tagline">34 רשתות · עדכון יומי</p>
          </div>
        )}

        {/* ── Search panel ──────────────────────────────────── */}
        <div style={{ position: 'relative' }}>
          <div className="search-panel-box">
            {/* Text search */}
            {(
              <div className="search-hero">
                <Search className="search-hero-icon" size={22} strokeWidth={1.8} />
                <input
                  ref={inputRef}
                  type="search"
                  className="search-hero-input"
                  placeholder="חפשי מוצר, מותג או ברקוד"
                  value={query}
                  onChange={e => handleInput(e.target.value)}
                  onFocus={() => setFocused(true)}
                  onBlur={() => setTimeout(() => setFocused(false), 200)}
                  autoFocus={!hasQuery}
                  aria-label="חיפוש מוצר"
                />
                {hasQuery ? (
                  <button className="search-hero-clear" onClick={clearSearch} aria-label="נקה חיפוש">
                    <X size={14} strokeWidth={2.5} />
                  </button>
                ) : (
                  <button className="search-hero-scan" onClick={() => navigate('/scan')} aria-label="סריקת ברקוד" title="סריקת ברקוד">
                    <Barcode size={20} strokeWidth={1.8} />
                  </button>
                )}
              </div>
            )}

            {/* Quick searches, right under the input */}
            {!hasQuery && (
              <div className="suggestions-row search-panel-chips">
                {POPULAR.map(({ label, q }) => (
                  <button key={q} className="suggestion-pill" onClick={() => startSearch(q)}>
                    <Search size={13} strokeWidth={2} />
                    {label}
                  </button>
                ))}
              </div>
            )}

            {!hasQuery && showHow && (
              <div className="search-steps-below">
                <button className="search-steps-close" onClick={closeHow} aria-label="הבנתי, סגור">
                  <X size={14} strokeWidth={2.5} />
                </button>
            {/* How it works: three steps in order, so the flow itself carries the meaning */}
            <div className="search-steps">
              <div className="search-steps-label">איך זה עובד</div>
              <ol className="search-steps-flow">
                <li className="search-step">
                  <SearchProductIcon />
                  <span>מחפשים מוצר</span>
                </li>
                <ChevronLeft size={16} strokeWidth={2} className="search-steps-arrow" aria-hidden />
                <li className="search-step">
                  <BuildBasketIcon />
                  <span>מוסיפים לסל</span>
                </li>
                <ChevronLeft size={16} strokeWidth={2} className="search-steps-arrow" aria-hidden />
                <li className="search-step">
                  <CompareTrendIcon />
                  <span>משווים בין הרשתות</span>
                </li>
              </ol>
            </div>
              </div>
            )}
            {!hasQuery && !showHow && (
              <button className="how-link" onClick={() => setShowHow(true)}>איך זה עובד?</button>
            )}
          </div>

          {/* Skeleton dropdown while loading */}
          {showDropdownSkeleton && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0,
              background: 'var(--surface)', border: '1.5px solid var(--line)',
              borderRadius: 'var(--r-lg)', boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
              zIndex: 200, overflow: 'hidden', marginTop: 4,
            }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px',
                  borderBottom: i < 4 ? '1px solid var(--line)' : 'none',
                }}>
                  <div className="skeleton" style={{ width: 44, height: 44, borderRadius: 10, flexShrink: 0 }} />
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <div className="skeleton" style={{ height: 14, width: `${55 + (i % 3) * 15}%` }} />
                    <div className="skeleton" style={{ height: 12, width: `${30 + (i % 2) * 15}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Autocomplete dropdown — outside search-panel-box to avoid overflow clipping */}
          {showDropdown && (
            <div ref={dropdownRef} style={{
              position: 'absolute', top: '100%', left: 0, right: 0,
              background: 'var(--surface)', border: '1.5px solid var(--line)',
              borderRadius: 'var(--r-lg)', boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
              zIndex: 200, overflow: 'hidden', marginTop: 4,
              maxHeight: dropdownMax, overflowY: 'auto',
              opacity: loading ? 0.6 : 1, transition: 'opacity 0.15s',
            }}>
              {sortedResults.slice(0, 8).map((product, i) => {
                const price = cheapest[product.barcode];
                return (
                  <div
                    key={product.barcode}
                    role="button"
                    tabIndex={0}
                    onMouseDown={() => navigate(`/product/${product.barcode}`)}
                    onKeyDown={e => e.key === 'Enter' && navigate(`/product/${product.barcode}`)}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 16px',
                      borderBottom: i < Math.min(sortedResults.length, 8) - 1 ? '1px solid var(--line)' : 'none',
                      border: 'none', background: 'transparent', cursor: 'pointer',
                      textAlign: 'start', fontFamily: 'var(--font-sans)',
                    }}
                  >
                    <ProductImage barcode={product.barcode} name={product.name} size={44} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      {(() => {
                        const { displayName, size, tailBrand } = extractProductDisplay(product.name, product.brand, product.unit_of_measure);
                        return (
                          <>
                            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--ink-900)',
                                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {displayName}
                              {size && <span className="size-chip">{size}</span>}
                            </div>
                            <div style={{ fontSize: 12, color: 'var(--ink-500)' }}>
                              {[product.barcode, tailBrand || cleanBrand(product.brand)].filter(s => s && s !== '---').join(' · ')}
                            </div>
                          </>
                        );
                      })()}
                    </div>
                    {price != null && (
                      <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--green-700)', flexShrink: 0 }}>
                        {fmt(price)}
                      </div>
                    )}
                    <QuickAddButton product={product} small />
                  </div>
                );
              })}
              {sortedResults.length > 8 && (
                <button
                  type="button"
                  className="dropdown-show-all"
                  onMouseDown={e => { e.preventDefault(); showAllResults(); }}
                  onClick={showAllResults}
                >
                  הצג את כל התוצאות (<span dir="ltr">{sortedResults.length}{hasMore ? '+' : ''}</span>)
                  <ChevronLeft size={14} strokeWidth={2.5} />
                </button>
              )}
            </div>
          )}
        </div>


        {/* ── Chains carousel ───────────────────────────────── */}
        {!hasQuery && (
          <>
            {shownBaskets.length > 0 && (
              <>
                <div className="section-header" style={{ marginBottom: 12 }}>
                  <div className="section-title">הסלים שלי</div>
                </div>
                <div className="card-row">
                  <button className="basket-card basket-card-new" onClick={openCreate}>
                    <Plus size={22} strokeWidth={2} />
                    <span>סל חדש</span>
                  </button>
                  {shownBaskets.map(b => {
                    const count = b.items.reduce((sum, i) => sum + i.quantity, 0);
                    return (
                      <button key={b.id} className="basket-card" onClick={() => { setActive(b.id); navigate('/basket'); }}>
                        <span className="basket-card-top">
                          <span className="basket-dot" style={{ background: b.color }} />
                          <span className="basket-card-name">{b.name}</span>
                        </span>
                        <span className="basket-card-meta">{count === 0 ? 'ריק' : count === 1 ? 'פריט אחד' : `${count} פריטים`}</span>
                        <span className="basket-card-price">
                          {b.lastCompare ? `₪${b.lastCompare.total.toFixed(2)}` : count === 0 ? 'עוד אין מוצרים' : 'השוואה ראשונה'}
                        </span>
                        <span className="basket-card-meta">
                          {b.lastCompare ? `נבדק ${timeAgo(b.lastCompare.at)}` : count === 0 ? 'חפשי והוסיפי' : 'לחצי להשוואה'}
                        </span>
                        {b.id === activeId && <span className="basket-card-active">פעיל</span>}
                      </button>
                    );
                  })}
                </div>
              </>
            )}

            <div className="section-header" style={{ marginBottom: 12 }}>
              <div>
                <div className="section-title">רשתות מובילות</div>
                <div className="section-subtitle">לחץ לסינון מחירים לפי רשת</div>
              </div>
              {chainFilter && (
                <button className="btn btn-ghost btn-sm" onClick={() => selectChain('')}
                  style={{ color: 'var(--ink-500)', fontSize: 12 }}>
                  <X size={13} strokeWidth={2.5} />
                  הסר סינון
                </button>
              )}
            </div>
            <ChainCarousel
              chains={FEATURED_CHAINS}
              selected={chainFilter}
              onSelect={selectChain}
              style={{ marginBottom: chainFilter ? 8 : 32 }}
            />
            {chainFilter && (
              <div className="near-stores-note" role="status" style={{ marginBottom: 16 }}>
                <MapPin size={18} strokeWidth={1.8} style={{ flexShrink: 0 }} />
                <span>
                  מסנן מחירים לפי רשת <strong>{chainFilter}</strong> — הסינון יחול על כל מוצר שתפתחי
                </span>
              </div>
            )}

          </>
        )}

        {/* ── Results ───────────────────────────────────────── */}
        {hasQuery && !showDropdown && !showDropdownSkeleton && (
          <>
            {error && (
              <div className="empty-state">
                <div className="empty-state-icon"><Search size={28} strokeWidth={1.5} /></div>
                <div className="empty-state-title">שגיאה בחיפוש</div>
                <div className="empty-state-desc">{error}</div>
                <button className="btn btn-secondary btn-sm" onClick={() => void doSearch(query)}>
                  נסה שוב
                </button>
              </div>
            )}

            {!loading && !error && results.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-icon"><Barcode size={28} strokeWidth={1.5} /></div>
                <div className="empty-state-title">לא נמצאו מוצרים</div>
                <div className="empty-state-desc">נסה שם אחר, מותג אחר, או הזן ברקוד מלא</div>
              </div>
            )}

            {!loading && !error && results.length > 0 && (
              <>
                <div className="section-header" style={{ marginBottom: 12 }}>
                  <div>
                    <div className="section-title">{results.length} תוצאות</div>
                    <div className="section-subtitle">
                      לחץ על מוצר לראות מחירים בכל הרשתות
                    </div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={clearSearch}>
                    <X size={14} strokeWidth={2.5} />
                    נקה
                  </button>
                </div>

                <div className="results-list" style={{ paddingBottom: 80 }}>
                  {results.map(product => {
                    const price = cheapest[product.barcode];
                    return (
                      <div
                        key={product.barcode}
                        role="button"
                        tabIndex={0}
                        className="product-card"
                        onClick={() => navigate(`/product/${product.barcode}`)}
                        onKeyDown={e => e.key === 'Enter' && navigate(`/product/${product.barcode}`)}
                        style={{ width: '100%', textAlign: 'start', border: '1px solid var(--line)', cursor: 'pointer' }}
                        aria-label={`${product.name}${price ? ` — הכי זול ${fmt(price)}` : ''}`}
                      >
                        <ProductImage barcode={product.barcode} name={product.name} size={56} />

                        <div className="product-card-body">
                          {(() => {
                            const { displayName, size, tailBrand } = extractProductDisplay(product.name, product.brand, product.unit_of_measure);
                            return (
                              <>
                                <div className="product-card-name">
                                  {displayName}
                                  {size && <span className="size-chip">{size}</span>}
                                </div>
                                <div className="product-card-meta">
                                  {[product.barcode, tailBrand || cleanBrand(product.brand)].filter(s => s && s !== '---').join(' · ')}
                                </div>
                              </>
                            );
                          })()}
                        </div>

                        <div className="product-card-price">
                          {price != null ? (
                            <>
                              <div className="product-card-price-value tabular savings-pop">
                                {fmt(price)}
                              </div>
                              <div className="product-card-price-label">הכי זול</div>
                            </>
                          ) : (
                            <div className="skeleton" style={{ width: 60, height: 24 }} />
                          )}
                        </div>

                        <QuickAddButton product={product} />

                        <ChevronLeft
                          size={18} strokeWidth={2} color="var(--ink-300)"
                          className="product-card-chevron"
                          style={{ flexShrink: 0 }}
                        />
                      </div>
                    );
                  })}
                </div>

                {hasMore && (
                  <div style={{ display: 'flex', justifyContent: 'center', paddingBottom: 80 }}>
                    <button className="btn btn-secondary" onClick={() => void loadMore()} disabled={loadingMore}>
                      {loadingMore ? 'טוען...' : 'טען עוד תוצאות'}
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}

      </div>

    </div>
  );
}
