import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Search, X, ChevronLeft, Barcode, Camera,
  MapPin, Navigation, TrendingDown,
} from 'lucide-react';

function SearchProductIcon() {
  // Magnifying glass with a mini price-comparison bar chart inside the lens
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden
      stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8.5" strokeWidth="2.1"/>
      <line x1="8.5"  y1="15" x2="8.5"  y2="11.5" strokeWidth="2"/>
      <line x1="12"   y1="15" x2="12"   y2="8.5"   strokeWidth="2"/>
      <line x1="15.5" y1="15" x2="15.5" y2="12.5"  strokeWidth="2"/>
      <line x1="7.5"  y1="15" x2="16.5" y2="15"    strokeWidth="1.5"/>
      <line x1="18.5" y1="18.5" x2="26" y2="26" strokeWidth="2.3"/>
    </svg>
  );
}

function BuildBasketIcon() {
  // Basket with two filled dots (groceries) framed by the handle arc
  return (
    <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden
      stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="10" cy="12" r="2.2" fill="currentColor" stroke="none"/>
      <circle cx="20" cy="12" r="2.2" fill="currentColor" stroke="none"/>
      <path d="M6.5 17 C6.5 6 23.5 6 23.5 17" strokeWidth="2.1" fill="none"/>
      <path d="M3.5 17 L5.5 27 Q6 29 8 29 L22 29 Q24 29 24.5 27 L26.5 17 Z"
        strokeWidth="2" fill="none"/>
      <line x1="4.5" y1="22.5" x2="25.5" y2="22.5" strokeWidth="1.5"/>
    </svg>
  );
}
import { searchProducts, compareProduct } from '../api/client';
import { ChainLogo } from '../components/ChainLogo';
import type { Product } from '../types';

/* ── constants ────────────────────────────────────────────── */
const FEATURED_CHAINS = [
  'שופרסל', 'רמי לוי', 'ויקטורי', 'מגה',
  'יוחננוף', 'טיב טעם', 'אושר עד', 'קרפור', 'חצי חינם',
];

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
function fmt(p: number) {
  return `₪${p.toFixed(2)}`;
}

/* ── sub-components ───────────────────────────────────────── */
function SkeletonCard() {
  return (
    <div className="product-card" style={{ pointerEvents: 'none', gap: 12 }}>
      <div className="skeleton" style={{ width: 56, height: 56, borderRadius: 12, flexShrink: 0 }} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div className="skeleton" style={{ height: 15, width: '72%' }} />
        <div className="skeleton" style={{ height: 12, width: '48%' }} />
        <div className="skeleton" style={{ height: 12, width: '38%' }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
        <div className="skeleton" style={{ height: 24, width: 64 }} />
        <div className="skeleton" style={{ height: 14, width: 48 }} />
      </div>
    </div>
  );
}

function BarcodePanel({ onSearch }: { onSearch: (q: string) => void }) {
  const [val, setVal] = useState('');
  return (
    <div className="barcode-panel">
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
      <div className="barcode-input-row">
        <input
          type="number"
          className="barcode-input"
          placeholder="הקלד מספר ברקוד..."
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && val && onSearch(val)}
          aria-label="ברקוד מוצר"
          autoFocus
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
  const [query, setQuery]     = useState(searchParams.get('q') ?? '');
  const [tab, setTab]         = useState<SearchTab>('text');
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [cheapest, setCheapest] = useState<Record<string, number>>({});
  const [locationMode, setLocationMode] = useState<'none' | 'city'>('none');
  const [cityInput, setCityInput] = useState('');
  const inputRef  = useRef<HTMLInputElement>(null);
  const debounce  = useRef<ReturnType<typeof setTimeout> | null>(null);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); setError(null); return; }
    setLoading(true); setError(null);
    try {
      setResults(await searchProducts(q.trim()));
    } catch {
      setError('לא הצלחנו לטעון. בדוק שהשרת פעיל ונסה שוב.');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const q = searchParams.get('q') ?? '';
    setQuery(q);
    if (q) void doSearch(q);
  }, [searchParams, doSearch]);

  // Fetch cheapest price per visible result
  useEffect(() => {
    if (!results.length) return;
    void (async () => {
      const map: Record<string, number> = {};
      await Promise.allSettled(
        results.slice(0, 12).map(async p => {
          try { map[p.barcode] = (await compareProduct(p.barcode)).cheapest_price; }
          catch { /* ignore */ }
        })
      );
      setCheapest(prev => ({ ...prev, ...map }));
    })();
  }, [results]);

  function handleInput(val: string) {
    setQuery(val);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setSearchParams(val.trim() ? { q: val.trim() } : {}, { replace: true });
    }, 320);
  }

  function clearSearch() {
    setQuery(''); setResults([]); setError(null);
    setSearchParams({}, { replace: true });
    inputRef.current?.focus();
  }

  function startSearch(q: string) {
    setQuery(q);
    setSearchParams({ q: q.trim() }, { replace: true });
  }

  const hasQuery = query.trim().length > 0;

  /* ── render ─────────────────────────────────────────────── */
  return (
    <div className="page-wrapper">
      <div className="container">

        {/* ── Hero ─────────────────────────────────────────── */}
        {!hasQuery && (
          <div className="hero-section">
            <h1 className="hero-title">השוואת מחירי סופרמרקט</h1>
            <p className="hero-tagline">34 רשתות · עדכון יומי</p>
          </div>
        )}

        {/* ── Mode cards (dual CTA) ─────────────────────────── */}
        {!hasQuery && (
          <div className="mode-cards">
            {/* Search product */}
            <button
              className="mode-card"
              onClick={() => { setTimeout(() => inputRef.current?.focus(), 50); }}
              aria-label="חיפוש מוצר בודד"
            >
              <div className="mode-card-icon green">
                <SearchProductIcon />
              </div>
              <div className="mode-card-title">חפש מוצר</div>
              <div className="mode-card-sub">השווה מחיר בין כל הרשתות</div>
            </button>

            {/* Build basket */}
            <button
              className="mode-card"
              onClick={() => navigate('/basket')}
              aria-label="בנה סל קניות"
            >
              <div className="mode-card-icon orange">
                <BuildBasketIcon />
              </div>
              <div className="mode-card-title">בנה סל</div>
              <div className="mode-card-sub">מצא את הרשת הזולה ביותר</div>
            </button>
          </div>
        )}

        {/* ── Search panel ──────────────────────────────────── */}
        <div className="search-panel-box">
          {/* Tabs */}
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

        {/* ── Location panel ────────────────────────────────── */}
        {!hasQuery && (
          <>
            <div className="location-panel">
              <button
                className={`location-btn${locationMode === 'none' ? '' : ''}`}
                onClick={() => {
                  if ('geolocation' in navigator) {
                    navigator.geolocation.getCurrentPosition(
                      () => alert('GPS: חנויות קרובות — תכונה תהיה זמינה עם השרת'),
                      () => alert('לא ניתן לקבל מיקום')
                    );
                  }
                }}
                aria-label="חנויות קרובות לפי מיקום"
              >
                <Navigation size={15} strokeWidth={2} />
                חנויות קרובות
              </button>

              <button
                className={`location-btn${locationMode === 'city' ? ' active' : ''}`}
                onClick={() => setLocationMode(m => m === 'city' ? 'none' : 'city')}
                aria-label="חפש לפי עיר"
              >
                <MapPin size={15} strokeWidth={2} />
                חפש לפי עיר
              </button>

              {locationMode === 'city' && (
                <div className="location-input-wrap">
                  <MapPin className="location-input-icon" size={14} strokeWidth={2} />
                  <input
                    type="text"
                    className="location-input"
                    placeholder="שם עיר או מיקוד..."
                    value={cityInput}
                    onChange={e => setCityInput(e.target.value)}
                    autoFocus
                    aria-label="עיר או מיקוד"
                  />
                </div>
              )}
            </div>

            {locationMode === 'city' && cityInput && (
              <div className="near-stores-note" role="status">
                <MapPin size={18} strokeWidth={1.8} style={{ flexShrink: 0 }} />
                <span>
                  חיפוש חנויות ב-<strong>{cityInput}</strong> — תכונה זו תהיה זמינה לאחר חיבור לשרת מיקומים.
                </span>
              </div>
            )}
          </>
        )}

        {/* ── Chains carousel ───────────────────────────────── */}
        {!hasQuery && (
          <>
            <div className="section-header" style={{ marginBottom: 12 }}>
              <div>
                <div className="section-title">רשתות מובילות</div>
                <div className="section-subtitle">לחץ לחיפוש מוצרים ברשת ספציפית</div>
              </div>
            </div>
            <div className="chains-row" style={{ marginBottom: 32, paddingBottom: 8 }}>
              {FEATURED_CHAINS.map(name => (
                <button
                  key={name}
                  onClick={() => startSearch(name)}
                  style={{ border: 'none', background: 'none', cursor: 'pointer', padding: 0 }}
                  aria-label={`חפש מוצרים ב${name}`}
                >
                  <ChainLogo name={name} size={52} showLabel />
                </button>
              ))}
            </div>

            {/* Popular searches */}
            <div className="section-header" style={{ marginBottom: 12 }}>
              <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <TrendingDown size={18} strokeWidth={1.8} color="var(--green-600)" />
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
        {hasQuery && (
          <>
            {loading && (
              <div className="results-list">
                {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
              </div>
            )}

            {!loading && error && (
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

                <div className="results-list">
                  {results.map(product => {
                    const price = cheapest[product.barcode];
                    return (
                      <button
                        key={product.barcode}
                        className="product-card"
                        onClick={() => navigate(`/product/${product.barcode}`)}
                        style={{ width: '100%', textAlign: 'start', border: '1px solid var(--line)', cursor: 'pointer' }}
                        aria-label={`${product.name}${price ? ` — הכי זול ${fmt(price)}` : ''}`}
                      >
                        {/* Product image placeholder */}
                        <div
                          style={{
                            width: 56, height: 56, borderRadius: 12,
                            background: 'var(--surface-100)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            flexShrink: 0, color: 'var(--ink-300)',
                          }}
                        >
                          <Barcode size={22} strokeWidth={1.5} />
                        </div>

                        <div className="product-card-body">
                          <div className="product-card-name">{product.name}</div>
                          <div className="product-card-meta">
                            {[product.brand, product.category, product.unit_of_measure]
                              .filter(Boolean).join(' · ')}
                          </div>
                          {product.barcode && (
                            <div className="product-card-barcode">{product.barcode}</div>
                          )}
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

                        <ChevronLeft
                          size={18} strokeWidth={2} color="var(--ink-300)"
                          style={{ transform: 'scaleX(-1)', flexShrink: 0 }}
                        />
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </>
        )}

      </div>
    </div>
  );
}
