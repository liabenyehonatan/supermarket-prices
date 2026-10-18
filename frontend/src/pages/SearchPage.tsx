import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ErrorState } from '../components/ErrorState';
import { Search, X, ChevronLeft, ChevronRight, Barcode, Plus, Trash2, SearchX } from 'lucide-react';
import { searchProducts, priceSummaryBatch, type PriceSummary } from '../api/client';
import { PromoBanner } from '../components/PromoBanner';
import { HowItWorksTour } from '../components/HowItWorksTour';
import { ProductCard, ProductCardSkeleton } from '../components/ProductCard';
import { useBasketWatch } from '../lib/basketWatch';
import { ExampleComparisons } from '../components/ExampleComparisons';
import { DealsStrip } from '../components/DealsStrip';
import { ChainCarousel } from '../components/ChainCarousel';
import { useBasket } from '../context/BasketContext';
import type { Product } from '../types';
import { useChainNames, readChainFilter, saveChainFilter } from '../lib/filters';
import { setMainSearchHidden } from '../lib/mainSearchVisibility';

/* ── constants ────────────────────────────────────────────── */
// Small pages load fast; the next one is fetched well before the end of the list is reached (infinite scroll)
const PAGE_SIZE = 10;
const SKELETON_CARDS = 4;

/* ── search snapshot: going back from a product returns to the same results and scroll position ── */
const SNAPSHOT_KEY = 'sali_search_snapshot_v2';   // v2: price summaries instead of bare prices
interface SearchSnapshot {
  q: string;
  results: Product[];
  hasMore: boolean;
  /** null: asked, and the product has no current price */
  summary: Record<string, PriceSummary | null>;
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
// The quick searches on the home page: a card with a photo each (public/quick), in a row that scrolls sideways
const POPULAR: { label: string; q: string; img: string }[] = [
  { label: 'חלב', q: 'חלב', img: '/quick/milk.jpg' },
  { label: 'ביצים', q: 'ביצים', img: '/quick/eggs.jpg' },
  { label: 'לחם', q: 'לחם', img: '/quick/bread.jpg' },
  { label: 'קוטג׳', q: 'קוטג', img: '/quick/cottage.jpg' },
  { label: 'גבינה צהובה', q: 'גבינה', img: '/quick/cheese.jpg' },
  { label: 'אורז', q: 'אורז', img: '/quick/rice.jpg' },
  { label: 'שמן זית', q: 'שמן זית', img: '/quick/olive-oil.jpg' },
  { label: 'יוגורט', q: 'יוגורט', img: '/quick/yogurt.jpg' },
  { label: 'עוף', q: 'עוף', img: '/quick/chicken.jpg' },
  { label: 'קפה', q: 'קפה', img: '/quick/coffee.jpg' },
];

/* ── main component ───────────────────────────────────────── */
export function SearchPage() {
  const navigate = useNavigate();
  const chainNames = useChainNames();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialSnap = useRef<SearchSnapshot | null>(readSnapshot(searchParams.get('q') ?? ''));
  const { baskets, activeId, setActive, openCreate, deleteBasket } = useBasket();
  const basketRowRef = useRef<HTMLDivElement>(null);
  const watch = useBasketWatch();
  // With one basket the card only appears once it has items; with several they are all listed
  const shownBaskets = baskets.length > 1 ? baskets : baskets.filter(b => b.items.length > 0);

  // Bring the active basket into view inside its row (without moving the page itself)
  useEffect(() => {
    const row = basketRowRef.current;
    const card = row?.querySelector<HTMLElement>('.basket-card.is-active');
    if (!row || !card) return;
    const r = row.getBoundingClientRect();
    const c = card.getBoundingClientRect();
    // Only scroll as far as needed to show the whole card, so the "new basket" card stays visible when it can
    const pad = 8;
    if (c.left < r.left + pad) row.scrollLeft += c.left - r.left - pad;
    else if (c.right > r.right - pad) row.scrollLeft += c.right - r.right + pad;
  }, [activeId, baskets.length]);
  const [query, setQuery]     = useState(searchParams.get('q') ?? '');
  const [results, setResults] = useState<Product[]>(() => initialSnap.current?.results ?? []);
  const [hasMore, setHasMore] = useState(() => initialSnap.current?.hasMore ?? false);
  const [loadingMore, setLoadingMore] = useState(false);
  const loadingMoreRef = useRef(false);
  const [moreError, setMoreError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [summary, setSummary] = useState<Record<string, PriceSummary | null>>(() => initialSnap.current?.summary ?? {});
  // City and chain filters also live in the URL (?city= / ?supermarket=) so a
  // refresh or a shared link keeps them; sessionStorage carries them across pages.
  const [chainFilter, setChainFilter] = useState<string>(() => searchParams.get('supermarket') ?? readChainFilter());
  const inputRef  = useRef<HTMLInputElement>(null);
  const debounce  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const panelRef  = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Only the newest request may change what is on screen: a slow answer for "חל" must not replace the
  // one for "חלב", and "load more" must not append to a different query.
  const searchSeq = useRef(0);

  const doSearch = useCallback(async (q: string) => {
    const seq = ++searchSeq.current;
    if (!q.trim()) { setResults([]); setHasMore(false); setError(null); setLoading(false); return; }
    setLoading(true); setError(null); setMoreError(false);
    try {
      const page = await searchProducts(q.trim(), PAGE_SIZE, 0);
      if (seq !== searchSeq.current) return;
      setResults(page);
      setHasMore(page.length === PAGE_SIZE);
    } catch {
      if (seq !== searchSeq.current) return;
      setError('לא הצלחנו לטעון את התוצאות כרגע. נסו שוב בעוד רגע.');
      setResults([]);
      setHasMore(false);
    } finally {
      if (seq === searchSeq.current) setLoading(false);
    }
  }, []);

  // The next page of the query on screen (the URL's, not what is half-typed in the field)
  const loadMore = useCallback(async (q: string, offset: number) => {
    if (!q || loadingMoreRef.current) return;
    const seq = searchSeq.current;
    loadingMoreRef.current = true;
    setLoadingMore(true); setMoreError(false);
    try {
      const page = await searchProducts(q, PAGE_SIZE, offset);
      if (seq !== searchSeq.current) return;
      setResults(prev => {
        const seen = new Set(prev.map(p => p.barcode));
        return [...prev, ...page.filter(p => !seen.has(p.barcode))];
      });
      setHasMore(page.length === PAGE_SIZE);
    } catch {
      if (seq === searchSeq.current) setMoreError(true);
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    const q = searchParams.get('q') ?? '';
    setQuery(q);
    setChainFilter(searchParams.get('supermarket') ?? readChainFilter());
    // The saved snapshot only applies to the very first render (coming back from a product page);
    // later searches (X, then Y, then X again) must load fresh results.
    const restore = initialSnap.current;
    initialSnap.current = null;
    if (restore && restore.q === q) {
      // Came back from a product page: the results are already here, just restore the scroll
      // 'instant': the page scrolls smoothly otherwise, and coming back would visibly slide down to where it was
      if (restore.scrollY > 0) setTimeout(() => window.scrollTo({ top: restore.scrollY, behavior: 'instant' as ScrollBehavior }), 0);
      return;
    }
    if (q) void doSearch(q);
  }, [searchParams, doSearch]);

  // Save the current results for the URL's query, so "back" can restore them
  useEffect(() => {
    const q = (searchParams.get('q') ?? '').trim();
    if (!q || loading || !results.length) return;
    writeSnapshot({ q, results, hasMore, summary, scrollY: readSnapshot(q)?.scrollY ?? 0 });
  }, [searchParams, results, hasMore, summary, loading]);

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
      // The page being left is still listening for a moment while the next one scrolls itself to the top:
      // that scroll must not become the position to come back to
      if (window.location.pathname !== '/') return;
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

  // The price line of every new result (cheapest price, where, per unit) in one request per page.
  // Each barcode is asked once; one the server has no price for is stored as null, so it is not asked again.
  const askedPrices = useRef(new Set<string>(Object.keys(initialSnap.current?.summary ?? {})));
  useEffect(() => {
    const missing = results.map(p => p.barcode).filter(b => !askedPrices.current.has(b));
    if (!missing.length) return;
    missing.forEach(b => askedPrices.current.add(b));
    void (async () => {
      // While the prices are being updated on the server a request can fail or take long: try again a little later
      // (twice) before leaving the cards to the next page's request.
      for (const wait of [0, 3000, 8000]) {
        if (wait) await new Promise(r => setTimeout(r, wait));
        try {
          const map = await priceSummaryBatch(missing);
          setSummary(prev => {
            const next = { ...prev };
            for (const b of missing) next[b] = map[b] ?? null;
            return next;
          });
          return;
        } catch {
          /* try again */
        }
      }
      missing.forEach(b => askedPrices.current.delete(b));   // still failing: asked again with the next page
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

  function clearSearch() {
    if (debounce.current) clearTimeout(debounce.current);
    setQuery(''); setResults([]); setHasMore(false); setError(null); setMoreError(false);
    setSearchParams({}, { replace: true });
    inputRef.current?.focus();
  }

  function startSearch(q: string) {
    if (debounce.current) clearTimeout(debounce.current);
    setQuery(q);
    setSearchParams({ q: q.trim() }, { replace: true });
  }

  const hasQuery = query.trim().length > 0;
  const settledQ = (searchParams.get('q') ?? '').trim();
  // Typed but not searched yet (the debounce), or searching: the grid shows placeholders, never "no results"
  const pending = loading || query.trim() !== settledQ;

  // Ordering of the full results list.
  const [sortMode, setSortMode] = useState<'relevance' | 'price'>('relevance');

  const orderedResults = (() => {
    if (sortMode === 'price') {
      return [...results].sort((a, b) => {
        const pa = summary[a.barcode] ? Number(summary[a.barcode]!.price) : null;
        const pb = summary[b.barcode] ? Number(summary[b.barcode]!.price) : null;
        if (pa == null || pb == null) return pa == null ? (pb == null ? 0 : 1) : -1;   // unknown prices last
        return pa - pb;
      });
    }
    return results;
  })();

  // Tell the header when the search field has gone up under it, so it can offer its own search button
  useEffect(() => {
    const el = panelRef.current?.querySelector('.search-hero');
    if (!el) return;
    const headerH = document.querySelector<HTMLElement>('.site-header')?.offsetHeight ?? 64;
    const io = new IntersectionObserver(([e]) => setMainSearchHidden(!e.isIntersecting), { rootMargin: `-${headerH}px 0px 0px 0px` });
    io.observe(el);
    return () => { io.disconnect(); setMainSearchHidden(false); };
  }, []);

  // The home blocks above and below the field fold away while a search is on (and come back when it is cleared),
  // so the field glides to the top instead of jumping. Folded blocks stay in the page, so they must not take focus.
  const heroRef = useRef<HTMLDivElement>(null);
  const bannerRef = useRef<HTMLDivElement>(null);
  const chipsWrapRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    for (const el of [heroRef.current, bannerRef.current, chipsWrapRef.current]) el?.toggleAttribute('inert', hasQuery);
  }, [hasQuery]);

  // Infinite scroll: the next page starts loading while the end of the list is still well below the screen
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore || pending || moreError || !settledQ) return;
    const io = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) void loadMore(settledQ, results.length);
    }, { rootMargin: '0px 0px 900px 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, pending, moreError, settledQ, results.length, loadMore]);

  const showSkeletonGrid = pending && results.length === 0 && !error;

  // The banner's button: bring the search field into view and put the cursor in it
  function focusSearch() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    inputRef.current?.focus({ preventScroll: true });
  }

  /* ── render ─────────────────────────────────────────────── */
  return (
    <div className="page-wrapper">
      <div className="container home-container">

        {/* ── Greeting ──────────────────────────────────────── */}
        <div className={`home-fold${hasQuery ? ' is-folded' : ''}`} ref={heroRef} aria-hidden={hasQuery || undefined}>
          <div className="home-fold-inner">
            <div className="greeting">
              <h1 className="greeting-title">מה נקנה היום? <span aria-hidden>👋</span></h1>
              <p className="greeting-sub">חפשו מוצר וראו איפה הכי זול</p>
            </div>
          </div>
        </div>

        {/* ── Search panel ──────────────────────────────────── */}
        <div className="search-panel-box" ref={panelRef}>
          <div className={`search-row${hasQuery ? ' has-back' : ''}`}>
          {hasQuery && (
            <button className="round-btn search-back" onClick={clearSearch} aria-label="חזרה לדף הבית">
              <ChevronRight size={20} strokeWidth={2} />
            </button>
          )}
          <div className="search-hero">
            <Search className="search-hero-icon" size={22} strokeWidth={1.8} />
            <input
              ref={inputRef}
              type="search"
              enterKeyHint="search"
              className="search-hero-input"
              placeholder="חפשו מוצר, מותג או ברקוד"
              value={query}
              onChange={e => handleInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.currentTarget.blur(); if (query.trim()) startSearch(query); } }}
              autoFocus={!hasQuery}
              aria-label="חיפוש מוצר"
            />
            {hasQuery ? (
              <button className="search-hero-clear" onClick={clearSearch} aria-label="ניקוי החיפוש">
                <X size={14} strokeWidth={2.5} />
              </button>
            ) : (
              <button className="search-hero-scan" onClick={() => navigate('/scan')} aria-label="סריקת ברקוד" title="סריקת ברקוד">
                <Barcode size={20} strokeWidth={1.8} />
              </button>
            )}
          </div>
          </div>
        </div>

        {/* ── Banner ────────────────────────────────────────── */}
        <div className={`home-fold${hasQuery ? ' is-folded' : ''}`} ref={bannerRef} aria-hidden={hasQuery || undefined}>
          <div className="home-fold-inner">
            <div className="hero-section">
              <PromoBanner onSearch={focusSearch} />
            </div>
          </div>
        </div>

        {/* ── Quick searches ────────────────────────────────────── */}
        <div className={`home-fold${hasQuery ? ' is-folded' : ''}`} ref={chipsWrapRef} aria-hidden={hasQuery || undefined}>
          <div className="home-fold-inner">
            <div className="section-header home-section-head categories-head">
              <div className="section-title">חיפוש מהיר</div>
            </div>
            <div className="category-row">
              {POPULAR.map(({ label, q, img }) => (
                <button key={q} className="category-card-tile" onClick={() => startSearch(q)}>
                  <img className="category-card-photo" src={img} alt="" aria-hidden width={72} height={72} loading="lazy" decoding="async" />
                  <span className="category-card-label">{label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* ── Home sections ─────────────────────────────────── */}
        {!hasQuery && (
          <div className="home-sections">
            {shownBaskets.length > 0 && (
              <>
                <div className="section-header home-section-head">
                  <div className="section-title">הסלים שלי</div>
                </div>
                <div className="card-row" ref={basketRowRef}>
                  <button className={`basket-card basket-card-new`} onClick={openCreate} aria-label="סל חדש">
                    <Plus size={22} strokeWidth={2} />
                    <span>סל חדש</span>
                  </button>
                  {shownBaskets.map(b => {
                    const count = b.items.reduce((sum, i) => sum + i.quantity, 0);
                    const isActive = b.id === activeId;
                    return (
                      <div key={b.id} className="basket-card-wrap">
                      <div
                        role="button"
                        tabIndex={0}
                        className={`basket-card${isActive ? ' is-active' : ''}`}
                        onClick={() => setActive(b.id)}
                        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setActive(b.id); } }}
                        aria-pressed={isActive}
                      >
                        <span className="basket-card-name">{b.name}</span>
                        <span className="basket-card-meta">{count === 0 ? 'ריק' : count === 1 ? 'פריט אחד' : `${count} פריטים`}</span>
                        {watch[b.id] && Math.abs(watch[b.id].diff) >= 0.5 && (
                          <span className={`basket-card-delta ${watch[b.id].diff < 0 ? 'down' : 'up'}`}>
                            {watch[b.id].diff < 0 ? 'ירד' : 'עלה'} <bdi dir="ltr">₪{Math.abs(watch[b.id].diff).toFixed(2)}</bdi>
                          </span>
                        )}
                        {isActive && (
                          <button
                            className="basket-card-cta"
                            onClick={e => { e.stopPropagation(); navigate('/basket'); }}
                          >
                            {count === 0 ? 'להוספה' : 'להשוואה'}
                            <ChevronLeft size={14} strokeWidth={2.5} aria-hidden />
                          </button>
                        )}
                      </div>
                      <button className="basket-card-remove" aria-label={`מחיקת ${b.name}`} onClick={() => deleteBasket(b.id)}>
                        <Trash2 size={14} strokeWidth={1.8} />
                      </button>
                      </div>
                    );
                  })}
                </div>
              </>
            )}

            <div className="section-header home-section-head">
              <div>
                <div className="section-title">מחירים לפי רשת</div>
                <div className="section-subtitle">
                  {chainFilter ? 'מציגים מחירים רק מהרשת שבחרת' : 'לחצו על רשת כדי לראות מחירים רק ממנה'}
                </div>
              </div>
            </div>
            <ChainCarousel
              chains={chainNames}
              selected={chainFilter}
              onSelect={selectChain}
              style={{ marginBottom: chainFilter ? 8 : 0 }}
            />
            {chainFilter && (
              <div className="chain-active-note" role="status">
                <span>מחירים רק מ<strong>{chainFilter}</strong> בכל האפליקציה</span>
                <button onClick={() => selectChain('')}>
                  <X size={13} strokeWidth={2.5} />
                  הציגו את כל הרשתות
                </button>
              </div>
            )}

            <ExampleComparisons />

            <DealsStrip chain={chainFilter} />
          </div>
        )}

        {/* ── Results ───────────────────────────────────────── */}
        {hasQuery && (
          <section className="results" aria-busy={pending || undefined} aria-label="תוצאות החיפוש">
            {error && <ErrorState title="שגיאה בחיפוש" text={error} onRetry={() => void doSearch(settledQ || query)} />}

            {!pending && !error && results.length === 0 && (
              <div className="empty-state">
                <div className="empty-state-icon"><SearchX size={28} strokeWidth={1.5} /></div>
                {(settledQ || query).trim().length < 2 ? (
                  <>
                    <div className="empty-state-title">הקלידו עוד אות או שתיים</div>
                    <div className="empty-state-desc">כדי לחפש צריך לפחות שני תווים, או ברקוד מלא</div>
                  </>
                ) : (
                  <>
                    <div className="empty-state-title">לא נמצאו מוצרים</div>
                    <div className="empty-state-desc">נסו שם אחר, מותג אחר, או הזינו ברקוד מלא</div>
                  </>
                )}
              </div>
            )}

            {(results.length > 0 || showSkeletonGrid) && !error && (
              <>
                <div className="results-head">
                  <h1 className="results-title">
                    תוצאות חיפוש עבור <bdi>״{settledQ || query.trim()}״</bdi>
                  </h1>
                  {results.length > 1 && (
                    <div className="sort-row" role="group" aria-label="מיון תוצאות">
                      {([['relevance', 'רלוונטיות'], ['price', 'הכי זול']] as const).map(([id, label]) => (
                        <button key={id} className={`sort-pill${sortMode === id ? ' on' : ''}`} aria-pressed={sortMode === id} onClick={() => setSortMode(id)}>
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className={`results-grid${pending && results.length > 0 ? ' is-stale' : ''}`}>
                  {orderedResults.map(product => (
                    <ProductCard key={product.barcode} product={product} summary={summary[product.barcode]} />
                  ))}
                  {(showSkeletonGrid || loadingMore || (hasMore && !moreError && !pending)) &&
                    Array.from({ length: showSkeletonGrid ? PAGE_SIZE : SKELETON_CARDS }).map((_, i) => <ProductCardSkeleton key={`sk-${i}`} />)}
                </div>

                {moreError && (
                  <div className="results-more-error" role="status">
                    לא הצלחנו לטעון עוד תוצאות.
                    <button className="btn btn-secondary btn-sm" onClick={() => void loadMore(settledQ, results.length)}>נסו שוב</button>
                  </div>
                )}
                <div ref={sentinelRef} className="results-sentinel" aria-hidden />
              </>
            )}
          </section>
        )}

      </div>

      <HowItWorksTour />
    </div>
  );
}
