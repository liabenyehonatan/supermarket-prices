import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowRight, MapPin, Truck, Plus, Minus,
  Check, Tag, ExternalLink, Navigation, X, ChevronDown, SlidersHorizontal,
} from 'lucide-react';
import { compareProduct, fetchCities, productHistory } from '../api/client';
import { ChainLogo } from '../components/ChainLogo';
import { ProductImage } from '../components/ProductImage';
import { useBasket } from '../context/BasketContext';
import type { ProductCompareResponse, PriceAtStore, PriceHistoryResponse } from '../types';
import { cleanBrand, extractProductDisplay } from '../lib/utils';
import { matchCity, onCityFilterChange, readCityFilter, readChainFilter, saveCityFilter, saveChainFilter } from '../lib/filters';
import { useCurrentCity, readMyCoords, type Coords } from '../lib/location';
import { PriceHistory } from '../components/PriceHistory';
import { FilterSheet } from '../components/FilterSheet';
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


// Prices older than a week get flagged; fresh ones need no label.
function isStale(iso?: string): boolean {
  return !!iso && Date.now() - new Date(iso).getTime() > 7 * 24 * 3_600_000;
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
  const [history, setHistory] = useState<PriceHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qty, setQty]     = useState(1);
  const [added, setAdded] = useState(false);
  const [cityFilter, setCityFilter] = useState(readCityFilter);
  useEffect(() => onCityFilterChange(setCityFilter), []);  // header chip
  const [cities, setCities] = useState<string[]>([]);
  useEffect(() => { fetchCities().then(setCities).catch(() => {}); }, []);
  const [chainFilter, setChainFilter] = useState(readChainFilter);
  const [filterOpen, setFilterOpen] = useState(false);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
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
    if (!barcode) return;
    setHistory(null);
    productHistory(barcode).then(setHistory).catch(() => {});  // optional extra; page works without it
  }, [barcode]);

  useEffect(() => {
    const ex = items.find(i => i.barcode === barcode);
    if (ex) setQty(ex.quantity);
  }, [items, barcode]);

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
  const { locate: handleGps, request: confirmLocation, pickCity: pickLocationCity, suggestedCity, locating: gpsLoading, problem: locationProblem, dismiss: dismissLocation } = useCurrentCity(onLocatedCity, setMyCoords);

  const namedPrices = data ? data.prices.filter(row => row.store_name) : [];
  const filteredPrices = namedPrices
    .filter(row => !cityFilter || row.store_city?.includes(cityFilter))
    .filter(row => !chainFilter || row.chain_name === chainFilter);

  const savings     = data ? Number(data.most_expensive_price) - Number(data.cheapest_price) : 0;
  const savingsPct  = data ? Math.round((savings / Number(data.most_expensive_price)) * 100) : 0;

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
                <ProductImage barcode={data.product.barcode} name={data.product.name} size={112} borderRadius={16} />

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

              {/* One headline price; the range and savings are supporting detail */}
              <div className="product-hero-price-row">
                <span className="product-hero-price-from">מ־</span>
                <span className="product-hero-price-min tabular">{fmt(data.cheapest_price)}</span>
              </div>
              {data.price_difference > 0.01 && (
                <div className="product-hero-range">
                  טווח מחירים <bdi dir="ltr">{fmt(data.cheapest_price)} – {fmt(data.most_expensive_price)}</bdi> · {data.prices.length} חנויות
                </div>
              )}
              {savings > 0.01 && (
                <div className="product-hero-savings">
                  חיסכון של עד <bdi dir="ltr">{fmt(savings)}</bdi> ({savingsPct}%)
                </div>
              )}
            </div>

            {history && <PriceHistory points={history.points} days={history.days} />}

            {/* ── Compare table ──────────────────────────────── */}
            <div className="section-header">
              <div>
                <div className="section-title">
                  {filteredPrices.length}{filteredPrices.length !== namedPrices.length ? ` מתוך ${namedPrices.length}` : ''} חנויות · מחיר נוכחי
                </div>
                <div className="section-subtitle">ממוין מהזול ליקר</div>
              </div>
            </div>

            {/* One chip opens the filter sheet (city, chain, my location) */}
            <div className="filter-bar">
              <button
                className={`filter-chip${(cityFilter || chainFilter) ? ' active' : ''}`}
                onClick={() => setFilterOpen(true)}
                aria-label="סינון חנויות"
              >
                <SlidersHorizontal size={15} strokeWidth={2} />
                {(cityFilter || chainFilter) ? [cityFilter, chainFilter].filter(Boolean).join(' · ') : 'סינון לפי עיר או רשת'}
                <ChevronDown size={13} strokeWidth={2.5} style={{ opacity: 0.6 }} />
              </button>
              {(cityFilter || chainFilter) && (
                <button
                  className="filter-chip-clear"
                  onClick={() => { setCityFilter(''); setChainFilter(''); saveCityFilter(''); saveChainFilter(''); }}
                  aria-label="נקי סינון"
                >
                  <X size={15} strokeWidth={2.5} />
                </button>
              )}
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
                const key = `${row.store_id}-${idx}`;
                const open = expandedRow === key;
                const name = row.store_name || row.chain_name;
                const km = myCoords && row.latitude != null && row.longitude != null
                  ? distanceKm(myCoords.lat, myCoords.lng, row.latitude, row.longitude)
                  : null;
                return (
                  <div
                    key={key}
                    className={`compare-row${isCheapest ? ' cheapest' : ''}`}
                    onClick={() => setExpandedRow(open ? null : key)}
                    aria-expanded={open}
                  >
                    <div className="compare-row-main">
                      <ChainLogo name={row.chain_name} size={44} />

                      <div className="compare-row-info">
                        <div className="compare-row-store">{name}</div>
                        {row.store_city && <div className="compare-row-city">{row.store_city}</div>}
                        {isStale(row.price_updated_at) && (
                          <div className="compare-row-city" style={{ color: 'var(--orange-700)', fontWeight: 600 }}>
                            מחיר ישן · עודכן לפני {timeAgo(row.price_updated_at)}
                          </div>
                        )}
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
                          <span className="compare-row-diff tabular">+{fmt(diff)}</span>
                        )}
                      </div>
                    </div>

                    {open && (
                      <div className="compare-row-more" onClick={e => e.stopPropagation()}>
                        {km != null && (
                          <div className="compare-row-city">{km.toFixed(1)} ק״מ ממך</div>
                        )}
                        {row.store_address && <div className="compare-row-city">{row.store_address}</div>}
                        <div className="compare-row-nav">
                          <a href={wazeUrl(row)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בוויז ל-${name}`}>
                            <Navigation size={10} strokeWidth={2} />
                            Waze
                          </a>
                          <a href={googleMapsUrl(row)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בגוגל מפות ל-${name}`}>
                            <MapPin size={10} strokeWidth={2} />
                            Maps
                          </a>
                          {row.delivery_url && (
                            <a href={row.delivery_url} target="_blank" rel="noopener noreferrer" className="compare-row-delivery" aria-label={`הזמן משלוח מ-${row.chain_name}`}>
                              <Truck size={10} strokeWidth={2} />
                              משלוח
                              <ExternalLink size={9} strokeWidth={2} />
                            </a>
                          )}
                        </div>
                      </div>
                    )}
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

      {filterOpen && (
        <FilterSheet
          city={cityFilter}
          cities={cities}
          chain={chainFilter}
          locating={gpsLoading}
          onCity={c => { setCityFilter(c); saveCityFilter(c); }}
          onChain={c => { setChainFilter(c); saveChainFilter(c); }}
          onLocate={handleGps}
          onClose={() => setFilterOpen(false)}
        />
      )}

      <LocationPrompt problem={locationProblem} onRetry={handleGps} onConfirm={confirmLocation} onPickCity={pickLocationCity} suggestedCity={suggestedCity} onClose={dismissLocation} />
    </div>
  );
}
