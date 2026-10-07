import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowRight, MapPin, Truck, Plus, Minus,
  Check, Tag, ExternalLink, Navigation, X, ChevronDown,
} from 'lucide-react';
import { compareProduct, fetchCities } from '../api/client';
import { ChainLogo } from '../components/ChainLogo';
import { ProductImage } from '../components/ProductImage';
import { useBasket } from '../context/BasketContext';
import type { ProductCompareResponse, PriceAtStore } from '../types';
import { cleanBrand, extractProductDisplay } from '../lib/utils';
import { FEATURED_CHAINS, matchCity, readCityFilter, readChainFilter, saveCityFilter, saveChainFilter } from '../lib/filters';
import { useCurrentCity, readMyCoords, type Coords } from '../lib/location';
import { LocationPrompt } from '../components/LocationPrompt';

function fmt(p: number | string) { return `₪${Number(p).toFixed(2)}`; }

// Great-circle distance between two lat/lng points, in km.
function distanceKm(aLat: number, aLng: number, bLat: number, bLng: number): number {
  const R = 6371;
  const dLat = (bLat - aLat) * Math.PI / 180;
  const dLng = (bLng - aLng) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(aLat * Math.PI / 180) * Math.cos(bLat * Math.PI / 180) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Waze and Google Maps both accept a free-text destination — no store coordinates
// needed, so this works today even though store geocoding hasn't run yet.
function storeNavQuery(row: PriceAtStore): string {
  return [row.store_name, row.store_address, row.store_city].filter(Boolean).join(', ') || row.chain_name;
}
function wazeUrl(row: PriceAtStore): string {
  return `https://waze.com/ul?q=${encodeURIComponent(storeNavQuery(row))}&navigate=yes`;
}
function googleMapsUrl(row: PriceAtStore): string {
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(storeNavQuery(row))}`;
}

function timeAgo(iso?: string): string {
  if (!iso) return '';
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3_600_000);
  if (h < 1) return 'פחות משעה';
  if (h < 24) return `${h} שע׳`;
  return `${Math.floor(h / 24)} י׳`;
}


function SkeletonRow() {
  return (
    <div className="compare-row" style={{ pointerEvents: 'none' }}>
      <div className="skeleton" style={{ width: 20, height: 14, borderRadius: 4 }} />
      <div className="skeleton" style={{ width: 44, height: 44, borderRadius: 10, flexShrink: 0 }} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 7 }}>
        <div className="skeleton" style={{ height: 14, width: '58%' }} />
        <div className="skeleton" style={{ height: 12, width: '38%' }} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7, alignItems: 'flex-end' }}>
        <div className="skeleton" style={{ height: 22, width: 64 }} />
      </div>
    </div>
  );
}

export function ProductPage() {
  const { barcode } = useParams<{ barcode: string }>();
  const navigate = useNavigate();
  const { addItem, items } = useBasket();
  const [data, setData]   = useState<ProductCompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qty, setQty]     = useState(1);
  const [added, setAdded] = useState(false);
  const [cityFilter, setCityFilter] = useState(readCityFilter);
  const [chainFilter, setChainFilter] = useState(readChainFilter);
  const [chainPickerOpen, setChainPickerOpen] = useState(false);
  const chainPickerRef = useRef<HTMLDivElement>(null);
  const cheapestRowRef = useRef<HTMLDivElement>(null);
  const [highlight, setHighlight] = useState(false);
  const [showCheapestPopup, setShowCheapestPopup] = useState(false);
  // Raw coordinates (not just the city) so each geocoded store can show its distance.
  const [myCoords, setMyCoords] = useState<Coords | null>(() => readMyCoords());

  useEffect(() => { window.scrollTo(0, 0); }, [barcode]);

  useEffect(() => {
    if (!barcode) return;
    setLoading(true); setError(null);
    compareProduct(barcode)
      .then(setData)
      .catch(() => setError('לא הצלחנו לטעון. תנסה שוב?'))
      .finally(() => setLoading(false));
  }, [barcode]);

  useEffect(() => {
    const ex = items.find(i => i.barcode === barcode);
    if (ex) setQty(ex.quantity);
  }, [items, barcode]);

  useEffect(() => {
    if (!showCheapestPopup) return;
    const close = () => setShowCheapestPopup(false);
    const timer = setTimeout(() => document.addEventListener('click', close), 0);
    return () => { clearTimeout(timer); document.removeEventListener('click', close); };
  }, [showCheapestPopup]);

  useEffect(() => {
    if (!chainPickerOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (chainPickerRef.current && !chainPickerRef.current.contains(e.target as Node)) {
        setChainPickerOpen(false);
      }
    };
    const timer = setTimeout(() => document.addEventListener('click', handleClick), 0);
    return () => { clearTimeout(timer); document.removeEventListener('click', handleClick); };
  }, [chainPickerOpen]);

  function handleAdd() {
    if (!data) return;
    addItem({ barcode: data.product.barcode, quantity: qty, name: data.product.name,
              brand: data.product.brand, unit: data.product.unit_of_measure });
    setAdded(true);
    setTimeout(() => setAdded(false), 2200);
  }

  const onLocatedCity = useCallback(async (found: string) => {
    const cities = await fetchCities().catch(() => [] as string[]);
    const city = matchCity(found, cities);
    setCityFilter(city);
    saveCityFilter(city);
  }, []);
  const { locate: handleGps, locating: gpsLoading, problem: locationProblem, dismiss: dismissLocation } = useCurrentCity(onLocatedCity, setMyCoords);

  const namedPrices = data ? data.prices.filter(row => row.store_name) : [];
  const filteredPrices = namedPrices
    .filter(row => !cityFilter || row.store_city?.includes(cityFilter))
    .filter(row => !chainFilter || row.chain_name === chainFilter);

  const savings     = data ? Number(data.most_expensive_price) - Number(data.cheapest_price) : 0;
  const savingsPct  = data ? Math.round((savings / Number(data.most_expensive_price)) * 100) : 0;
  const avgPrice    = data
    ? data.prices.reduce((s, p) => s + Number(p.price), 0) / data.prices.length
    : 0;

  return (
    <div className="page-wrapper">
      {/* The sticky add-to-basket bar floats above the bottom nav, on top of the page's
          own bottom padding — reserve extra room so short pages (e.g. a filter with no
          matching stores) don't end up with their last bit of content hidden under it. */}
      <div className="container" style={{ paddingBottom: data ? 96 : 0 }}>

        {/* Back */}
        <button className="page-back" onClick={() => navigate(-1)}>
          <ArrowRight size={18} strokeWidth={2} />
          חזרה לתוצאות
        </button>

        {/* ── Product hero ─────────────────────────────────── */}
        {loading && (
          <div className="product-hero" style={{ marginBottom: 8 }}>
            <div style={{ display: 'flex', gap: 16 }}>
              <div className="skeleton" style={{ width: 72, height: 72, borderRadius: 12, flexShrink: 0 }} />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div className="skeleton" style={{ height: 20, width: '70%' }} />
                <div className="skeleton" style={{ height: 14, width: '45%' }} />
                <div className="skeleton" style={{ height: 44, width: '55%', marginTop: 6 }} />
              </div>
            </div>
          </div>
        )}

        {error && (
          <div className="empty-state">
            <div className="empty-state-title">שגיאה בטעינה</div>
            <div className="empty-state-desc">{error}</div>
            <button className="btn btn-secondary btn-sm" onClick={() => barcode && void compareProduct(barcode).then(setData)}>
              נסה שוב
            </button>
          </div>
        )}

        {data && !loading && (
          <>
            {/* Product card */}
            <div className="product-hero">
              <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                <ProductImage barcode={data.product.barcode} name={data.product.name} size={72} />

                <div style={{ flex: 1, minWidth: 0 }}>
                  {(() => {
                    const { displayName, size } = extractProductDisplay(data.product.name, data.product.brand, data.product.unit_of_measure);
                    const mfr = cleanBrand(data.product.manufacturer || data.product.brand);
                    return (
                      <>
                        <h1 className="product-hero-name">{displayName}{size ? `, ${size}` : ''}</h1>
                        <div className="product-hero-meta">
                          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-400)' }}>
                            ({[data.product.barcode, mfr].filter(s => s && s !== '---').join(' · ')})
                          </span>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>

              {/* Price range */}
              <div className="product-hero-price-row">
                <span className="product-hero-price-min tabular">{fmt(data.cheapest_price)}</span>
                {data.price_difference > 0.01 && (
                  <>
                    <span className="product-hero-price-dash">–</span>
                    <span className="product-hero-price-max tabular">{fmt(data.most_expensive_price)}</span>
                  </>
                )}
              </div>

            </div>

            {/* ── Quick stats ────────────────────────────────── */}
            <div className="stats-bar">
              <div
                className="stat-item highlight savings-with-icon"
                style={{ cursor: 'pointer' }}
                onClick={() => setShowCheapestPopup(v => !v)}
                title="לחץ לראות את הסניף"
              >
                <div className="stat-item-text">
                  <div className="stat-label">הכי זול ↓</div>
                  <div className="stat-value">{fmt(data.cheapest_price)}</div>
                  <div className="stat-sub">{namedPrices[0]?.chain_name}</div>
                </div>
                <span className="stat-icon-wrap stat-icon-wrap-cheapest">
                  <img src="/icons/cheapest-tag.webp" alt="" aria-hidden />
                </span>
              </div>
              <div className="stat-item savings-with-icon">
                <div className="stat-item-text">
                  <div className="stat-label">ממוצע</div>
                  <div className="stat-value">{fmt(avgPrice)}</div>
                  <div className="stat-sub">{data.prices.length} חנויות</div>
                </div>
                <span className="stat-icon-wrap stat-icon-wrap-plain">
                  <img src="/icons/avg-calculator.png" alt="" aria-hidden />
                </span>
              </div>
              <div className="stat-item savings savings-with-icon">
                <div className="stat-item-text">
                  <div className="stat-label">חסכון</div>
                  <div className="stat-value">{fmt(savings)}</div>
                  <div className="stat-sub">{savingsPct}%</div>
                </div>
                <span className="stat-icon-wrap">
                  <img src="/icons/piggy-bank.webp" alt="" aria-hidden />
                </span>
              </div>
            </div>

            {/* Cheapest store popup */}
            {showCheapestPopup && namedPrices[0] && (
              <div
                style={{
                  background: 'var(--surface)', border: '1.5px solid var(--green-500)',
                  borderRadius: 'var(--r-lg)', boxShadow: '0 4px 16px rgba(0,0,0,0.10)',
                  padding: '14px 16px', marginBottom: 12,
                }}
                onClick={e => e.stopPropagation()}
              >
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--green-600)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  הכי זול בכל ישראל
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <ChainLogo name={namedPrices[0].chain_name} size={44} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink-900)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {namedPrices[0].store_name}
                    </div>
                    {namedPrices[0].store_city && (
                      <div style={{ fontSize: 12, color: 'var(--ink-400)', display: 'flex', alignItems: 'center', gap: 3, marginTop: 2 }}>
                        <MapPin size={11} strokeWidth={1.8} />
                        {namedPrices[0].store_city}
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--green-600)' }}>
                    {fmt(namedPrices[0].price)}
                  </div>
                </div>
                {cityFilter && (
                  <button
                    style={{
                      marginTop: 12, width: '100%', padding: '8px 0',
                      background: 'var(--green-600)', color: '#fff',
                      border: 'none', borderRadius: 'var(--r-md)',
                      fontSize: 13, fontWeight: 600, cursor: 'pointer',
                      fontFamily: 'var(--font-sans)',
                    }}
                    onClick={() => {
                      setShowCheapestPopup(false);
                      setCityFilter('');
                      saveCityFilter('');
                      setTimeout(() => {
                        cheapestRowRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        setHighlight(true);
                        setTimeout(() => setHighlight(false), 2000);
                      }, 100);
                    }}
                  >
                    הסר סינון עיר וגלול אליו
                  </button>
                )}
              </div>
            )}

            {/* ── Compare table ──────────────────────────────── */}
            <div className="section-header">
              <div>
                <div className="section-title">
                  {filteredPrices.length}{(cityFilter || chainFilter) ? ` מתוך ${namedPrices.length}` : ''} חנויות · מחיר נוכחי
                </div>
                <div className="section-subtitle">ממוין מהזול ליקר</div>
              </div>
            </div>

            {/* Chain filter picker */}
            <div ref={chainPickerRef} style={{ position: 'relative', marginBottom: 10 }}>
              <button
                onClick={() => setChainPickerOpen(v => !v)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  background: chainFilter ? 'var(--green-50)' : 'var(--surface)',
                  border: `1.5px solid ${chainFilter ? 'var(--green-200)' : 'var(--line)'}`,
                  borderRadius: 20, padding: '5px 10px 5px 8px',
                  fontSize: 13, fontWeight: 600,
                  color: chainFilter ? 'var(--green-700)' : 'var(--ink-500)',
                  cursor: 'pointer', fontFamily: 'var(--font-sans)',
                }}
                aria-label="בחרי רשת לסינון"
              >
                {chainFilter
                  ? <><ChainLogo name={chainFilter} size={20} />{chainFilter}</>
                  : 'כל הרשתות'
                }
                <ChevronDown size={13} strokeWidth={2.5} style={{ marginInlineStart: 2, opacity: 0.6 }} />
              </button>

              {chainFilter && (
                <button
                  onClick={() => { setChainFilter(''); saveChainFilter(''); }}
                  style={{
                    display: 'inline-flex', alignItems: 'center',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--ink-400)', padding: '4px 6px', marginInlineStart: 4,
                  }}
                  aria-label="הסר סינון רשת"
                >
                  <X size={13} strokeWidth={2.5} />
                </button>
              )}

              {chainPickerOpen && (
                <div style={{
                  position: 'absolute', top: 'calc(100% + 6px)', insetInlineStart: 0,
                  background: 'var(--surface-0)', border: '1.5px solid var(--line)',
                  borderRadius: 'var(--r-lg)', boxShadow: '0 8px 24px rgba(0,0,0,0.16)',
                  zIndex: 300, padding: '10px 8px',
                  display: 'flex', flexWrap: 'wrap', gap: 4, maxWidth: 320,
                }}>
                  {FEATURED_CHAINS.map(name => (
                    <button
                      key={name}
                      onClick={() => {
                        const next = chainFilter === name ? '' : name;
                        setChainFilter(next);
                        saveChainFilter(next);
                        setChainPickerOpen(false);
                      }}
                      style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3,
                        padding: '6px 8px', borderRadius: 10, cursor: 'pointer',
                        border: chainFilter === name ? '2px solid var(--green-500)' : '2px solid transparent',
                        background: chainFilter === name ? 'var(--green-50)' : 'transparent',
                        fontFamily: 'var(--font-sans)',
                      }}
                    >
                      <ChainLogo name={name} size={36} />
                      <span style={{ fontSize: 10, color: 'var(--ink-600)', fontWeight: chainFilter === name ? 700 : 400 }}>
                        {name}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* City filter — a single input, always editable. It used to switch to a
                read-only "chip" display the instant cityFilter became truthy, which
                happened after the very first keystroke — so typing a second letter was
                impossible. The clear button now just overlays the input instead. */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
              <div style={{ position: 'relative', flex: 1 }}>
                <MapPin size={15} strokeWidth={2} style={{
                  position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
                  color: 'var(--ink-400)', pointerEvents: 'none',
                }} />
                <input
                  type="text"
                  placeholder="סנן לפי עיר..."
                  value={cityFilter}
                  onChange={e => { setCityFilter(e.target.value); saveCityFilter(e.target.value); }}
                  style={{
                    width: '100%', boxSizing: 'border-box',
                    padding: cityFilter ? '10px 36px' : '10px 36px 10px 12px',
                    border: '1.5px solid var(--line)', borderRadius: 'var(--r-lg)',
                    fontSize: 14, background: 'var(--surface)', color: 'var(--ink-900)',
                    fontFamily: 'var(--font-sans)', outline: 'none',
                  }}
                />
                {cityFilter && (
                  <button
                    onClick={() => { setCityFilter(''); saveCityFilter(''); }}
                    style={{
                      position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
                      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                      width: 20, height: 20, borderRadius: '50%',
                      background: 'var(--surface-200)', border: 'none', cursor: 'pointer',
                      color: 'var(--ink-500)', padding: 0,
                    }}
                    aria-label="הסר סינון עיר"
                  >
                    <X size={12} strokeWidth={2.5} />
                  </button>
                )}
              </div>
              <button
                onClick={handleGps}
                disabled={gpsLoading}
                title="מצא את העיר שלי"
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '10px 14px', borderRadius: 'var(--r-lg)',
                  border: '1.5px solid var(--line)', background: 'var(--surface)',
                  color: gpsLoading ? 'var(--ink-300)' : 'var(--green-600)',
                  cursor: gpsLoading ? 'default' : 'pointer',
                  fontSize: 13, fontWeight: 600, fontFamily: 'var(--font-sans)',
                  whiteSpace: 'nowrap',
                }}
              >
                <Navigation size={15} strokeWidth={2} />
                {gpsLoading ? 'מאתר...' : 'לפי מיקום נוכחי'}
              </button>
            </div>

            {filteredPrices.length === 0 && namedPrices.length > 0 && (cityFilter || chainFilter) && (
              <div className="empty-state" style={{ padding: '32px 0' }}>
                <div className="empty-state-title">
                  {cityFilter && chainFilter
                    ? `אין חנויות ${chainFilter} ב${cityFilter}`
                    : cityFilter
                      ? `אין חנויות ב${cityFilter}`
                      : `אין חנויות ${chainFilter} עם מוצר זה`}
                </div>
                <div className="empty-state-desc">נסי לשנות את הסינון</div>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'center', flexWrap: 'wrap' }}>
                  {cityFilter && (
                    <button className="btn btn-secondary btn-sm" onClick={() => { setCityFilter(''); saveCityFilter(''); }}>
                      הסר סינון עיר
                    </button>
                  )}
                  <button className="btn btn-secondary btn-sm" onClick={() => { setCityFilter(''); setChainFilter(''); saveCityFilter(''); saveChainFilter(''); }}>
                    הצג את כל החנויות
                  </button>
                </div>
              </div>
            )}

            <div className="compare-table" style={{ marginBottom: 20 }}>
              {filteredPrices.map((row, idx) => {
                const isCheapest = idx === 0;
                const diff = Number(row.price) - Number(filteredPrices[0]?.price ?? row.price);
                return (
                  <div
                    key={`${row.store_id}-${idx}`}
                    ref={isCheapest ? cheapestRowRef : undefined}
                    className={`compare-row${isCheapest ? ' cheapest' : ''}`}
                    style={isCheapest && highlight ? {
                      outline: '2.5px solid var(--green-400)',
                      borderRadius: 'var(--r-lg)',
                      transition: 'outline 0.3s',
                    } : undefined}
                  >
                    <span className="compare-row-rank">{idx + 1}</span>

                    <ChainLogo name={row.chain_name} size={44} />

                    <div className="compare-row-info">
                      <div className="compare-row-store">{row.store_name || row.chain_name}</div>
                      {row.store_city && (
                        <div className="compare-row-city">
                          <MapPin size={11} strokeWidth={1.8} style={{ display: 'inline', verticalAlign: 'middle', marginInlineEnd: 3 }} />
                          {row.store_city}
                        </div>
                      )}
                      {row.price_updated_at && (
                        <div className="compare-row-city" style={{ color: 'var(--ink-300)' }}>
                          עודכן לפני {timeAgo(row.price_updated_at)}
                        </div>
                      )}
                      {/* Distance needs the store's own coordinates, which aren't geocoded
                          yet (see project notes) — this will start appearing on its own
                          once that runs, with no further change needed here. */}
                      {myCoords && row.latitude != null && row.longitude != null && (
                        <div className="compare-row-city" style={{ color: 'var(--ink-400)' }}>
                          {distanceKm(myCoords.lat, myCoords.lng, row.latitude, row.longitude).toFixed(1)} ק״מ ממך
                        </div>
                      )}
                      <div className="compare-row-nav">
                        <a
                          href={wazeUrl(row)}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          aria-label={`נווט בוויז ל-${row.store_name || row.chain_name}`}
                        >
                          <Navigation size={10} strokeWidth={2} />
                          Waze
                        </a>
                        <a
                          href={googleMapsUrl(row)}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          aria-label={`נווט בגוגל מפות ל-${row.store_name || row.chain_name}`}
                        >
                          <MapPin size={10} strokeWidth={2} />
                          Maps
                        </a>
                      </div>
                    </div>

                    <div className="compare-row-right">
                      <span className={`compare-row-price tabular${isCheapest ? ' text-green' : ''}`}>
                        {fmt(row.price)}
                      </span>

                      {isCheapest && (
                        <span className="badge badge-cheapest" style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                          <Tag size={10} strokeWidth={2.5} />
                          הכי זול
                        </span>
                      )}

                      {!isCheapest && diff > 0 && (
                        <span className="badge badge-neutral tabular" style={{ fontSize: 11 }}>
                          +{fmt(diff)}
                        </span>
                      )}

                      {row.delivery_url && (
                        <a
                          href={row.delivery_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="compare-row-delivery"
                          onClick={e => e.stopPropagation()}
                          aria-label={`הזמן משלוח מ-${row.chain_name}`}
                        >
                          <Truck size={10} strokeWidth={2} />
                          משלוח
                          <ExternalLink size={9} strokeWidth={2} />
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Bottom spacing for sticky bar */}
            <div style={{ height: 88 }} />
          </>
        )}

        {/* Loading skeleton */}
        {loading && (
          <>
            <div className="stats-bar" style={{ marginBottom: 8 }}>
              {[0,1,2].map(i => (
                <div key={i} className="stat-item">
                  <div className="skeleton" style={{ height: 11, width: '60%' }} />
                  <div className="skeleton" style={{ height: 22, width: '70%', marginTop: 4 }} />
                </div>
              ))}
            </div>
            <div className="compare-table" style={{ marginBottom: 20 }}>
              {Array.from({ length: 7 }).map((_, i) => <SkeletonRow key={i} />)}
            </div>
          </>
        )}

      </div>

      {/* ── Sticky add-to-basket bar ───────────────────────── */}
      {data && (
        <div className="add-to-basket-bar">
          <div className="add-to-basket-qty">
            <button className="qty-btn" onClick={() => setQty(q => Math.max(1, q - 1))} aria-label="הורד כמות">
              <Minus size={14} strokeWidth={2.5} />
            </button>
            <span className="qty-value">{qty}</span>
            <button className="qty-btn" onClick={() => setQty(q => q + 1)} aria-label="הגדל כמות">
              <Plus size={14} strokeWidth={2.5} />
            </button>
          </div>

          <button
            className={`btn btn-full ${added ? 'btn-secondary' : 'btn-primary'}`}
            style={{ flex: 1, transition: 'background 0.2s' }}
            onClick={handleAdd}
          >
            {added ? (
              <><Check size={18} strokeWidth={2.5} /> נוסף לסל</>
            ) : (
              'הוסף לסל'
            )}
          </button>
        </div>
      )}

      <LocationPrompt problem={locationProblem} onRetry={handleGps} onClose={dismissLocation} />
    </div>
  );
}
