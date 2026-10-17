import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowRight, MapPin, Truck, Plus, Minus, Share2, ShoppingBasket,
  Check, ExternalLink, Navigation, X, ChevronDown, SlidersHorizontal,
} from 'lucide-react';
import { compareProduct, fetchCities } from '../api/client';
import { StoreRow } from '../components/StoreRow';
import { money, safeHttpUrl } from '../lib/safe';
import { useDocumentTitle } from '../lib/useDocumentTitle';
import { cityName, isOnlineStore, navQuery, storeAddress, storeSubtitle } from '../lib/store';
import { ProductImage } from '../components/ProductImage';
import { useBasket } from '../context/BasketContext';
import type { ProductCompareResponse, PriceAtStore } from '../types';
import { cleanBrand, extractProductDisplay } from '../lib/utils';
import { unitPriceLabel } from '../lib/productMeta';
import { matchCity, onCityFilterChange, readCityFilter, readChainFilter, saveCityFilter, saveChainFilter } from '../lib/filters';
import { useCurrentCity, readMyCoords, type Coords } from '../lib/location';
import { FilterSheet } from '../components/FilterSheet';
import { flyToBasket } from '../lib/flyToBasket';
import { LocationPrompt } from '../components/LocationPrompt';

const NEARBY_KM = 15;

function fmt(p: number | string) { return money(p); }

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

// Waze and Google Maps both accept a free-text destination — no store coordinates needed.
function storeNavQuery(row: PriceAtStore): string {
  return navQuery({ chain: row.chain_name, name: row.store_name, address: row.store_address, city: row.store_city }) || row.chain_name;
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


const STORES_PAGE = 40;

// Prices older than a week get flagged; fresh ones need no label. A chain's full file lists every
// item, and an item's own price_updated_at only moves when its price changes, so it can be years old
// for a price confirmed today. Judge freshness by when we last saw the price in a file (scraped_at).
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
  const [showAll, setShowAll] = useState(false);
  // Popular products are sold in ~1,500 stores; drawing them all at once is slow on a phone.
  const [visibleCount, setVisibleCount] = useState(STORES_PAGE);
  // Nearby mode is an explicit opt-in per visit — a position left over from an earlier
  // session must never make the page claim these stores are "near you".
  const [nearbyActive, setNearbyActive] = useState(false);
  const nearbyRef = useRef(false);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  // Raw coordinates (not just the city) so each geocoded store can show its distance.
  const [myCoords, setMyCoords] = useState<Coords | null>(() => readMyCoords());
  const heroImageRef = useRef<HTMLDivElement>(null);

  useEffect(() => { window.scrollTo(0, 0); }, [barcode]);

  useDocumentTitle(data ? `${data.product.name} — השוואת מחירים | סלי` : null);

  // Loads (or reloads) the product. `isCurrent` lets a slow answer for a product the user already left
  // be dropped instead of overwriting the page.
  const load = useCallback((code: string, isCurrent: () => boolean) => {
    setLoading(true); setError(null);
    compareProduct(code)
      .then(result => { if (isCurrent()) setData(result); })
      .catch(() => { if (isCurrent()) setError('לא הצלחנו לטעון את המוצר כרגע. נסי שוב בעוד רגע.'); })
      .finally(() => { if (isCurrent()) setLoading(false); });
  }, []);

  useEffect(() => {
    if (!barcode) return;
    let current = true;
    setData(null); setQty(1); setExpandedRow(null);      // never show the previous product while this one loads
    load(barcode, () => current);
    return () => { current = false; };
  }, [barcode, load]);

  useEffect(() => {
    const ex = items.find(i => i.barcode === barcode);
    if (ex) setQty(ex.quantity);
  }, [items, barcode]);

  // The phone's own share sheet where there is one; otherwise copy the link.
  function handleShare() {
    if (!data) return;
    const url = window.location.href;
    if (navigator.share) {
      navigator.share({ title: data.product.name, url }).catch(() => {});
    } else {
      navigator.clipboard?.writeText(url).catch(() => {});
    }
  }

  function goBack() {
    if (window.history.length > 1) navigate(-1); else navigate('/');
  }

  function handleAdd() {
    if (!data) return;
    addItem({ barcode: data.product.barcode, quantity: qty, name: data.product.name,
              brand: data.product.brand, unit: data.product.unit_of_measure }, () => {
      flyToBasket(heroImageRef.current);
      setAdded(true);
      setTimeout(() => setAdded(false), 2200);
    });
  }

  const onLocatedCity = useCallback(async (found: string) => {
    const cities = await fetchCities().catch(() => [] as string[]);
    if (nearbyRef.current) return;  // nearby mode filters by distance, not by city
    const city = matchCity(found, cities);
    setCityFilter(city);
    saveCityFilter(city);
  }, []);
  const { locate: handleGps, request: confirmLocation, pickCity: pickLocationCity, suggestedCity, locating: gpsLoading, problem: locationProblem, dismiss: dismissLocation } = useCurrentCity(onLocatedCity, setMyCoords);

  const namedPrices = data ? data.prices.filter(row => row.store_name) : [];
  const matchingPrices = namedPrices
    .filter(row => !cityFilter || cityName(row.store_city).includes(cityFilter))
    .filter(row => !chainFilter || row.chain_name === chainFilter);
  // Nearby mode: stores within NEARBY_KM of the user. Only geocoded stores have
  // coordinates, so "all stores" stays one tap away.
  const nearbyPrices = nearbyActive && myCoords
    ? namedPrices
        .filter(row => !chainFilter || row.chain_name === chainFilter)
        .filter(row => row.latitude != null && row.longitude != null
          && distanceKm(myCoords.lat, myCoords.lng, row.latitude, row.longitude) <= NEARBY_KM)
        // Cheapest first; among equal prices the closest store comes first.
        .sort((a, b) => Number(a.price) - Number(b.price)
          || distanceKm(myCoords.lat, myCoords.lng, a.latitude!, a.longitude!)
           - distanceKm(myCoords.lat, myCoords.lng, b.latitude!, b.longitude!))
    : [];
  const nearbyMode = nearbyPrices.length > 0 && !showAll;
  const filteredPrices = nearbyMode ? nearbyPrices : matchingPrices;
  const shownPrices = filteredPrices.slice(0, visibleCount);
  // A new product or filter starts again from the first page.
  useEffect(() => { setVisibleCount(STORES_PAGE); }, [barcode, cityFilter, chainFilter, showAll, nearbyActive]);

  function setNearby(on: boolean) {
    nearbyRef.current = on;
    setNearbyActive(on);
    setShowAll(false);
  }
  function toggleNearby() {
    if (nearbyActive) { setNearby(false); return; }
    setNearby(true);
    setCityFilter(''); saveCityFilter('');
    if (!myCoords) handleGps();
  }

  // The headline numbers describe the stores listed below (rows without a store name are not listed).
  const listedPrices = namedPrices.map(row => Number(row.price)).filter(Number.isFinite);
  const headlineMin = listedPrices.length ? Math.min(...listedPrices) : Number(data?.cheapest_price ?? 0);
  const headlineMax = listedPrices.length ? Math.max(...listedPrices) : Number(data?.most_expensive_price ?? 0);
  const savings     = data ? headlineMax - headlineMin : 0;
  const savingsPct  = data && headlineMax > 0 ? Math.round((savings / headlineMax) * 100) : 0;
  // Where the cheapest price is: one chain by name, several by count
  const cheapestChains = [...new Set(namedPrices.filter(row => Math.abs(Number(row.price) - headlineMin) < 0.005).map(row => row.chain_name))];
  const cheapestWhere = cheapestChains.length === 1 ? `ב${cheapestChains[0]}` : cheapestChains.length > 1 ? `ב-${cheapestChains.length} רשתות` : '';
  const cheapestRow = namedPrices.find(row => Math.abs(Number(row.price) - headlineMin) < 0.005);
  const perUnit = cheapestRow && data ? unitPriceLabel(cheapestRow.price, cheapestRow.unit_price, data.product.unit_of_measure) : null;

  return (
    <div className="page-wrapper">
      {/* The sticky add-to-basket bar floats above the bottom nav, on top of the page's
          own bottom padding — reserve extra room so short pages (e.g. a filter with no
          matching stores) don't end up with their last bit of content hidden under it. */}
      <div className="container" style={{ paddingBottom: data ? 96 : 0 }}>

        {/* ── Picture stage: back, title, share, and the product picture large ── */}
        <div className="product-stage">
          <div className="product-stage-bar">
            <button className="round-btn" onClick={goBack} aria-label="חזרה">
              <ArrowRight size={20} strokeWidth={2} />
            </button>
            <span className="product-stage-title">פרטי מוצר</span>
            <button className="round-btn" onClick={handleShare} aria-label="שיתוף" disabled={!data}>
              <Share2 size={18} strokeWidth={2} />
            </button>
          </div>
          <div className="product-stage-image" ref={heroImageRef}>
            {data && !loading
              ? <ProductImage barcode={data.product.barcode} name={data.product.name} imageUrl={data.product.image_url} size={200} borderRadius={0} />
              : !error && <div className="skeleton" style={{ width: 180, height: 180, borderRadius: 24 }} aria-hidden />}
          </div>
        </div>

        {loading && (
          <div className="product-sheet" aria-hidden>
            <div className="skeleton" style={{ height: 13, width: '30%' }} />
            <div className="skeleton" style={{ height: 22, width: '75%', marginTop: 10 }} />
            <div className="skeleton" style={{ height: 30, width: '40%', marginTop: 20 }} />
            <div className="skeleton" style={{ height: 13, width: '55%', marginTop: 8 }} />
          </div>
        )}

        {error && (
          <div className="empty-state">
            <div className="empty-state-title">שגיאה בטעינה</div>
            <div className="empty-state-desc">{error}</div>
            <button className="btn btn-secondary btn-sm" onClick={() => barcode && load(barcode, () => true)}>
              נסה שוב
            </button>
          </div>
        )}

        {data && !loading && (
          <>
            {/* Product sheet over the picture: maker and quantity, name and size, then the two numbers that matter */}
            <div className="product-sheet">
              {(() => {
                const { displayName, size } = extractProductDisplay(data.product.name, data.product.brand, data.product.unit_of_measure);
                const mfr = cleanBrand(data.product.manufacturer || data.product.brand);
                return (
                  <>
                    <div className="product-sheet-top">
                      <span className="product-sheet-maker">{mfr && mfr !== '---' ? mfr : ''}</span>
                      <div className="product-qty" role="group" aria-label="כמות">
                        <button className="product-qty-btn" onClick={() => setQty(q => Math.max(1, q - 1))} aria-label="הורד כמות" disabled={qty <= 1}>
                          <Minus size={14} strokeWidth={2.5} />
                        </button>
                        <span className="product-qty-value tabular">{qty}</span>
                        <button className="product-qty-btn is-plus" onClick={() => setQty(q => q + 1)} aria-label="הגדל כמות">
                          <Plus size={14} strokeWidth={2.5} />
                        </button>
                      </div>
                    </div>
                    <h1 className="product-sheet-name">
                      {displayName}
                      {size && <span className="size-chip">{size}</span>}
                    </h1>
                  </>
                );
              })()}

              {/* The price as plain text, the way a shelf tag reads: cheapest price, how much less than the dearest, where */}
              <div className="product-price">
                <div className="product-price-row">
                  <span className="product-price-value tabular" dir="ltr">{fmt(headlineMin)}</span>
                  {savings > 0.01 && <span className="product-price-off">עד {savingsPct}% פחות</span>}
                  {perUnit && <span className="product-price-unit tabular"><bdi dir="ltr">{perUnit.price}</bdi> {perUnit.per}</span>}
                </div>
                <div className="product-price-note">
                  {`הכי זול${cheapestWhere ? ` ${cheapestWhere}` : ''}`}
                  {savings > 0.01 && <> · הכי יקר <s><bdi dir="ltr">{fmt(headlineMax)}</bdi></s></>}
                </div>
              </div>
            </div>

            {/* ── Compare table ──────────────────────────────── */}
            <div className="section-header">
              <div>
                <h2 className="section-title">{nearbyMode ? 'הכי זול לידך' : 'איפה הכי זול?'}</h2>
                <div className="section-subtitle">
                  {nearbyMode
                    ? `${filteredPrices.length} חנויות עד ${NEARBY_KM} ק״מ ממך, מהזול ליקר`
                    : `${filteredPrices.length}${filteredPrices.length !== namedPrices.length ? ` מתוך ${namedPrices.length}` : ''} חנויות, מהזול ליקר`}
                </div>
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
              <button
                className={`filter-chip${nearbyPrices.length > 0 ? ' active' : ''}`}
                onClick={toggleNearby}
                aria-pressed={nearbyActive}
              >
                <Navigation size={15} strokeWidth={2} />
                {gpsLoading && nearbyActive ? 'מאתר...' : 'לידי'}
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

            {nearbyActive && myCoords && !gpsLoading && nearbyPrices.length === 0 && (
              <div className="compare-row-city" style={{ marginBottom: 10 }}>
                לא נמצאו חנויות עד {NEARBY_KM} ק״מ ממך. מוצגות כל החנויות.
              </div>
            )}

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

            <div className="compare-table store-list" style={{ marginBottom: 20 }}>
              {shownPrices.map((row, idx) => {
                const isCheapest = idx === 0;
                const diff = Number(row.price) - Number(filteredPrices[0]?.price ?? row.price);
                const key = `${row.store_id}-${idx}`;
                const name = row.store_name || row.chain_name;
                const promos = row.promotions ?? [];
                const km = myCoords && row.latitude != null && row.longitude != null
                  ? distanceKm(myCoords.lat, myCoords.lng, row.latitude, row.longitude)
                  : null;
                return (
                  <StoreRow
                    key={key}
                    chain={row.chain_name}
                    name={row.chain_name}
                    city={storeSubtitle({ chain: row.chain_name, name: row.store_name, address: row.store_address, city: row.store_city })}
                    warning={isStale(row.scraped_at ?? row.price_updated_at) ? `מחיר ישן · עודכן לפני ${timeAgo(row.scraped_at ?? row.price_updated_at)}` : undefined}
                    promo={promos[0]?.description}
                    price={row.price}
                    isCheapest={isCheapest}
                    cheapestLabel={nearbyMode ? 'הכי זול לידך' : 'הכי זול'}
                    diff={diff}
                    open={expandedRow === key}
                    onToggle={() => setExpandedRow(expandedRow === key ? null : key)}
                  >
                    {promos.length > 0 && (
                      <div className="store-row-promos">
                        <div className="store-row-sub">מבצעים ברשת, כפי שהרשת פרסמה (המחיר למעלה הוא מחיר המדף):</div>
                        <ul>
                          {promos.map((p, i) => (
                            <li key={i}>
                              {p.description}
                              {p.ends_at && <span className="store-row-promo-end"> · עד {new Date(p.ends_at).toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric' })}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {km != null && <div className="store-row-sub">{km.toFixed(1)} ק״מ ממך</div>}
                    {(() => {
                      const addr = storeAddress({ chain: row.chain_name, name: row.store_name, address: row.store_address, city: row.store_city });
                      return addr ? <div className="store-row-sub">כתובת: {addr}</div> : null;
                    })()}
                    <div className="store-row-actions">
                      {!isOnlineStore({ chain: row.chain_name, name: row.store_name, address: row.store_address }) && (<>

                      <a href={wazeUrl(row)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בוויז ל-${name}`}>
                        <Navigation size={12} strokeWidth={2} />
                        Waze
                      </a>
                      <a href={googleMapsUrl(row)} target="_blank" rel="noopener noreferrer" aria-label={`נווט בגוגל מפות ל-${name}`}>
                        <MapPin size={12} strokeWidth={2} />
                        Maps
                      </a>
                      </>)}
                      {safeHttpUrl(row.delivery_url) && (
                        <a href={safeHttpUrl(row.delivery_url) as string} target="_blank" rel="noopener noreferrer" aria-label={`הזמן משלוח מ-${row.chain_name}`}>
                          <Truck size={12} strokeWidth={2} />
                          משלוח
                          <ExternalLink size={10} strokeWidth={2} />
                        </a>
                      )}
                    </div>
                  </StoreRow>
                );
              })}
            </div>

            {filteredPrices.length > visibleCount && (
              <button className="btn btn-secondary btn-full" style={{ marginBottom: 20 }} onClick={() => setVisibleCount(c => c + STORES_PAGE)}>
                הצג עוד {Math.min(STORES_PAGE, filteredPrices.length - visibleCount)} חנויות · נותרו {filteredPrices.length - visibleCount}
              </button>
            )}

            {nearbyMode && (
              <button className="btn btn-secondary btn-full" style={{ marginBottom: 20 }} onClick={() => setShowAll(true)}>
                הצג את כל {matchingPrices.length} החנויות
              </button>
            )}
            {nearbyActive && nearbyPrices.length > 0 && showAll && (
              <button className="btn btn-secondary btn-full" style={{ marginBottom: 20 }} onClick={() => setShowAll(false)}>
                חזרה לחנויות קרובות
              </button>
            )}

            {/* Bottom spacing for sticky bar */}
            <div style={{ height: 88 }} />
          </>
        )}

        {/* Loading skeleton */}
        {loading && (
          <>
            <div className="compare-table store-list" style={{ marginBottom: 20 }}>
              {Array.from({ length: 7 }).map((_, i) => <SkeletonRow key={i} />)}
            </div>
          </>
        )}

      </div>

      {/* ── Sticky add-to-basket bar ───────────────────────── */}
      {data && (
        <div className="add-to-basket-bar product-buy-bar">
          <div className="product-buy-total">
            <span className="product-buy-label">{qty > 1 ? `${qty} יח׳, החל מ-` : 'החל מ-'}</span>
            <span className="product-buy-price tabular" dir="ltr">{fmt(Number(data.cheapest_price) * qty)}</span>
          </div>
          <button
            className={`btn btn-full ${added ? 'btn-secondary' : 'btn-primary'} product-buy-btn`}
            onClick={handleAdd}
          >
            {added
              ? <><Check size={18} strokeWidth={2.5} /> נוסף לסל</>
              : <><ShoppingBasket size={18} strokeWidth={2} /> הוסף לסל</>}
          </button>
        </div>
      )}

      {filterOpen && (
        <FilterSheet
          city={cityFilter}
          cities={cities}
          chain={chainFilter}
          locating={gpsLoading}
          onCity={c => { setNearby(false); setCityFilter(c); saveCityFilter(c); }}
          onChain={c => { setChainFilter(c); saveChainFilter(c); }}
          onLocate={() => { setNearby(false); handleGps(); }}
          onClose={() => setFilterOpen(false)}
        />
      )}

      <LocationPrompt problem={locationProblem} onRetry={handleGps} onConfirm={confirmLocation} onPickCity={pickLocationCity} suggestedCity={suggestedCity} onClose={dismissLocation} />
    </div>
  );
}
