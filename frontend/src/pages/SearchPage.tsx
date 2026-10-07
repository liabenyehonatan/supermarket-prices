import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search, X, ChevronLeft, Barcode, Camera,
  MapPin, Navigation, TrendingUp, VideoOff, Plus, Check,
} from 'lucide-react';
import { BrowserMultiFormatReader } from '@zxing/browser';

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

import { searchProducts, compareProduct, fetchCities } from '../api/client';
import { ProductImage } from '../components/ProductImage';
import { HeroBanner } from '../components/HeroBanner';
import { ChainCarousel } from '../components/ChainCarousel';
import { LocationPrompt } from '../components/LocationPrompt';
import { useBasket } from '../context/BasketContext';
import type { Product } from '../types';
import { cleanBrand, extractProductDisplay } from '../lib/utils';
import { FEATURED_CHAINS, matchCity, readCityFilter, readChainFilter, saveCityFilter, saveChainFilter } from '../lib/filters';
import { useCurrentCity } from '../lib/location';

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

type SearchTab = 'text' | 'barcode' | 'image';

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

function BarcodePanel({ onSearch }: { onSearch: (q: string) => void }) {
  const [val, setVal] = useState('');
  const [scanning, setScanning] = useState(false);
  const [camError, setCamError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const readerRef = useRef<BrowserMultiFormatReader | null>(null);
  const controlsRef = useRef<{ stop: () => void } | null>(null);

  const stopScan = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
    readerRef.current = null;
    setScanning(false);
  }, []);

  const startScan = useCallback(async () => {
    setCamError(null);
    setScanning(true);
    try {
      const reader = new BrowserMultiFormatReader();
      readerRef.current = reader;
      const controls = await reader.decodeFromConstraints(
        { video: { facingMode: 'environment' } },
        videoRef.current!,
        (result, err) => {
          if (result) {
            stopScan();
            onSearch(result.getText());
          }
          if (err && !(err.name === 'NotFoundException')) {
            setCamError('לא הצלחנו לגשת למצלמה');
            stopScan();
          }
        }
      );
      controlsRef.current = controls;
    } catch {
      setCamError('לא ניתן לגשת למצלמה — אשרי גישה בדפדפן');
      setScanning(false);
    }
  }, [onSearch, stopScan]);

  useEffect(() => () => { controlsRef.current?.stop(); }, []);

  return (
    <div className="barcode-panel">
      {/* Camera viewfinder */}
      {scanning && (
        <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden',
                      background: '#000', marginBottom: 16, aspectRatio: '4/3' }}>
          <video ref={videoRef} style={{ width: '100%', height: '100%', objectFit: 'cover' }} autoPlay muted playsInline />
          {/* Scan frame overlay */}
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}>
            <div style={{ width: 200, height: 120, border: '2px solid rgba(255,255,255,0.9)', borderRadius: 8,
                          boxShadow: '0 0 0 9999px rgba(0,0,0,0.45)' }} />
          </div>
          <button
            onClick={stopScan}
            style={{ position: 'absolute', top: 10, insetInlineEnd: 10,
                     background: 'rgba(0,0,0,0.6)', border: 'none', borderRadius: '50%',
                     width: 36, height: 36, display: 'flex', alignItems: 'center',
                     justifyContent: 'center', cursor: 'pointer', color: '#fff' }}
            aria-label="סגור מצלמה"
          >
            <X size={18} strokeWidth={2.5} />
          </button>
        </div>
      )}
      {!scanning && (
        <div className="barcode-visual" aria-hidden>
          <div className="barcode-bars">
            {[4,6,3,7,5,8,3,6,5,4,7,6,3,5,8,4,6,3].map((h, i) => (
              <div key={i} className="barcode-bar" style={{ height: h * 3.5 }} />
            ))}
          </div>
          <span style={{ fontSize: 11, color: 'var(--ink-400)', fontFamily: 'var(--font-mono)' }}>
            729000006685
          </span>
        </div>
      )}
      {camError && (
        <div style={{ color: 'var(--red-500)', fontSize: 13, marginBottom: 10, textAlign: 'center' }}>{camError}</div>
      )}
      {/* Camera scan button */}
      <button
        className={`btn ${scanning ? 'btn-secondary' : 'btn-primary'} btn-full`}
        style={{ marginBottom: 12, gap: 8 }}
        onClick={scanning ? stopScan : startScan}
      >
        {scanning ? <><VideoOff size={16} strokeWidth={2} /> עצור סריקה</> : <><Camera size={16} strokeWidth={2} /> סרוק ברקוד עם מצלמה</>}
      </button>
      {/* Manual entry */}
      <div className="barcode-input-row">
        <input
          type="number"
          className="barcode-input"
          placeholder="או הקלד מספר ברקוד..."
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && val && onSearch(val)}
          aria-label="ברקוד מוצר"
        />
        <button
          className="btn btn-primary"
          disabled={!val}
          onClick={() => val && onSearch(val)}
          style={{ flexShrink: 0, gap: 6 }}
        >
          <Barcode size={16} strokeWidth={2} />
          חפש
        </button>
      </div>

    </div>
  );
}

function ImagePanel() {
  const fileRef = useRef<HTMLInputElement>(null);
  return (
    <div className="image-upload-panel">
      <input ref={fileRef} type="file" accept="image/*" className="sr-only" aria-label="העלה תמונת מוצר" />
      <div
        className="image-drop-zone"
        onClick={() => fileRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && fileRef.current?.click()}
        aria-label="העלה תמונה לזיהוי מוצר"
      >
        <div className="image-drop-zone-icon">
          <Camera size={28} strokeWidth={1.5} />
        </div>
        <div className="image-drop-zone-title">העלה תמונת מוצר</div>
        <div className="image-drop-zone-sub">גרור לכאן, לחץ לבחירה, או שלח מהאלבום</div>
      </div>
    </div>
  );
}

/* ── main component ───────────────────────────────────────── */
export function SearchPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialSnap = useRef<SearchSnapshot | null>(readSnapshot(searchParams.get('q') ?? ''));
  const [query, setQuery]     = useState(searchParams.get('q') ?? '');
  const [tab, setTab]         = useState<SearchTab>('text');
  const [results, setResults] = useState<Product[]>(() => initialSnap.current?.results ?? []);
  const [hasMore, setHasMore] = useState(() => initialSnap.current?.hasMore ?? false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [cheapest, setCheapest] = useState<Record<string, number>>(() => initialSnap.current?.cheapest ?? {});
  const [locationMode, setLocationMode] = useState<'none' | 'city'>('none');
  const [cityInput, setCityInput] = useState(readCityFilter);
  const [cities, setCities] = useState<string[]>([]);
  const [cityFocused, setCityFocused] = useState(false);
  const [chainFilter, setChainFilter] = useState<string>(readChainFilter);
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

  // Fetch cheapest price per visible result
  useEffect(() => {
    const missing = results.filter(p => cheapest[p.barcode] == null);
    if (!missing.length) return;
    void (async () => {
      const map: Record<string, number> = {};
      await Promise.allSettled(
        missing.map(async p => {
          try { map[p.barcode] = (await compareProduct(p.barcode)).cheapest_price; }
          catch { /* ignore */ }
        })
      );
      setCheapest(prev => ({ ...prev, ...map }));
    })();
  }, [results]);

  // Load available cities once
  useEffect(() => {
    fetchCities().then(setCities).catch(() => {});
  }, []);

  function handleInput(val: string) {
    setQuery(val);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setSearchParams(val.trim() ? { q: val.trim() } : {}, { replace: true });
    }, 320);
  }

  function saveCity(city: string) {
    setCityInput(city);
    if (!city || cities.includes(city)) saveCityFilter(city);
  }

  const selectCity = useCallback((city: string) => {
    setCityInput(city);
    saveCityFilter(city);
    setCityFocused(false);
    setLocationMode('none');
  }, []);

  // "By current location": fill the city filter from the device's position
  const onLocatedCity = useCallback((found: string) => selectCity(matchCity(found, cities)), [cities, selectCity]);
  const { locate, locating, problem: locationProblem, dismiss: dismissLocation } = useCurrentCity(onLocatedCity);

  function selectChain(name: string) {
    const next = chainFilter === name ? '' : name;
    setChainFilter(next);
    saveChainFilter(next);
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

        {/* ── Location panel ────────────────────────────────── */}
        <div className="location-panel">
          <button
            className="location-btn"
            onClick={locate}
            disabled={locating}
            aria-label="סנן לפי המיקום הנוכחי"
          >
            <Navigation size={15} strokeWidth={2} />
            {locating ? 'מאתר מיקום...' : 'לפי מיקום נוכחי'}
          </button>

          <button
            className={`location-btn${locationMode === 'city' || cityInput ? ' active' : ''}`}
            onClick={() => setLocationMode(m => m === 'city' ? 'none' : 'city')}
            aria-label="חפש לפי עיר"
          >
            <MapPin size={15} strokeWidth={2} />
            {cityInput || 'חפש לפי עיר'}
            {cityInput && (
              <span
                role="button"
                aria-label="הסר סינון עיר"
                onClick={e => { e.stopPropagation(); saveCity(''); }}
                style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  marginInlineStart: 4, width: 16, height: 16,
                  borderRadius: '50%', background: 'var(--green-200)',
                  color: 'var(--green-700)', flexShrink: 0,
                }}
              >
                <X size={10} strokeWidth={3} />
              </span>
            )}
          </button>

          {locationMode === 'city' && (() => {
            const q = cityInput.trim();
            const matched = (q && !cities.includes(q))
              ? cities.filter(c => c.includes(q)).slice(0, 8)
              : cities.slice(0, 8);
            const isValid = !q || cities.includes(q);
            const showSuggestions = cityFocused && matched.length > 0;
            return (
              <div className="location-input-wrap" style={{ position: 'relative' }}>
                <MapPin className="location-input-icon" size={14} strokeWidth={2} />
                <input
                  type="text"
                  className="location-input"
                  placeholder="הקלידי שם עיר..."
                  value={cityInput}
                  onChange={e => saveCity(e.target.value)}
                  onFocus={() => setCityFocused(true)}
                  onBlur={() => setTimeout(() => setCityFocused(false), 180)}
                  autoFocus
                  aria-label="עיר לסינון"
                  style={{ borderColor: !isValid && q ? 'var(--red-400)' : undefined }}
                />
                {cityInput && (
                  <button
                    onMouseDown={() => { saveCity(''); setCityFocused(false); }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer',
                             color: 'var(--ink-400)', display: 'flex', padding: 4, flexShrink: 0 }}
                    aria-label="נקה עיר"
                  >
                    <X size={13} strokeWidth={2.5} />
                  </button>
                )}
                {/* City suggestions dropdown */}
                {showSuggestions && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0,
                    background: 'var(--surface-0)', border: '1.5px solid var(--line)',
                    borderRadius: 'var(--r-lg)', boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
                    zIndex: 300, overflow: 'hidden',
                    backdropFilter: 'none',
                  }}>
                    {matched.map((city, i) => (
                      <button
                        key={city}
                        onMouseDown={() => selectCity(city)}
                        style={{
                          width: '100%', display: 'flex', alignItems: 'center', gap: 10,
                          padding: '10px 14px',
                          borderBottom: i < matched.length - 1 ? '1px solid var(--line)' : 'none',
                          border: 'none', background: 'transparent', cursor: 'pointer',
                          textAlign: 'start', fontFamily: 'var(--font-sans)',
                          fontSize: 14, color: 'var(--ink-900)',
                        }}
                      >
                        <MapPin size={14} strokeWidth={2} color="var(--ink-400)" style={{ flexShrink: 0 }} />
                        {city}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })()}
        </div>

        {cityInput && cities.includes(cityInput) && (
          <div className="near-stores-note" role="status" style={{ marginBottom: 12 }}>
            <MapPin size={18} strokeWidth={1.8} style={{ flexShrink: 0 }} />
            <span>
              מסנן חנויות ב-<strong>{cityInput}</strong> — הסינון יחול על כל מוצר שתפתחי
            </span>
            <button
              onClick={() => saveCity('')}
              style={{
                marginInlineStart: 'auto', flexShrink: 0,
                display: 'flex', alignItems: 'center',
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'inherit', opacity: 0.7, padding: 2,
              }}
              aria-label="הסר סינון עיר"
            >
              <X size={15} strokeWidth={2.5} />
            </button>
          </div>
        )}

        {/* ── Search panel ──────────────────────────────────── */}
        <div style={{ position: 'relative' }}>
          <div className="search-panel-box">
            {/* Tabs */}
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

            <div className="search-tabs" role="tablist" aria-label="שיטת חיפוש">
              {([
                { id: 'text' as SearchTab,    icon: <Search size={14} strokeWidth={2} />,   label: 'חיפוש טקסט' },
                { id: 'barcode' as SearchTab, icon: <Barcode size={14} strokeWidth={2} />,  label: 'ברקוד' },
                { id: 'image' as SearchTab,   icon: <Camera size={14} strokeWidth={2} />,   label: 'תמונה' },
              ] as { id: SearchTab; icon: React.ReactNode; label: string }[]).map(t => (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={tab === t.id}
                  className={`search-tab${tab === t.id ? ' active' : ''}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.icon}
                  {t.label}
                </button>
              ))}
            </div>

            {/* Text search */}
            {tab === 'text' && (
              <div className="search-hero">
                <Search className="search-hero-icon" size={22} strokeWidth={1.8} />
                <input
                  ref={inputRef}
                  type="search"
                  className="search-hero-input"
                  placeholder="שם מוצר בעברית, מותג, או ברקוד..."
                  value={query}
                  onChange={e => handleInput(e.target.value)}
                  onFocus={() => setFocused(true)}
                  onBlur={() => setTimeout(() => setFocused(false), 200)}
                  autoFocus={!hasQuery}
                  aria-label="חיפוש מוצר"
                />
                {hasQuery && (
                  <button className="search-hero-clear" onClick={clearSearch} aria-label="נקה חיפוש">
                    <X size={14} strokeWidth={2.5} />
                  </button>
                )}
              </div>
            )}

            {/* Barcode */}
            {tab === 'barcode' && (
              <BarcodePanel onSearch={q => { setTab('text'); startSearch(q); }} />
            )}

            {/* Image */}
            {tab === 'image' && <ImagePanel />}
          </div>

          {/* Skeleton dropdown while loading */}
          {showDropdownSkeleton && tab === 'text' && (
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
          {showDropdown && tab === 'text' && (
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

            {/* Popular searches */}
            <div className="section-header" style={{ marginBottom: 12 }}>
              <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <TrendingUp size={18} strokeWidth={1.8} color="var(--green-600)" />
                חיפושים פופולריים
              </div>
            </div>
            <div className="suggestions-row">
              {POPULAR.map(({ label, q }) => (
                <button key={q} className="suggestion-pill" onClick={() => startSearch(q)}>
                  <Search size={13} strokeWidth={2} />
                  {label}
                </button>
              ))}
            </div>
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

      <LocationPrompt problem={locationProblem} onRetry={locate} onClose={dismissLocation} />
    </div>
  );
}
