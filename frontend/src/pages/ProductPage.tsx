import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowRight, TrendingDown, MapPin, Truck, Plus, Minus,
  Check, Barcode, Tag, ExternalLink,
} from 'lucide-react';
import { compareProduct } from '../api/client';
import { ChainLogo } from '../components/ChainLogo';
import { useBasket } from '../context/BasketContext';
import type { ProductCompareResponse } from '../types';

function fmt(p: number) { return `₪${p.toFixed(2)}`; }

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

  function handleAdd() {
    if (!data) return;
    addItem({ barcode: data.product.barcode, quantity: qty, name: data.product.name,
              brand: data.product.brand, unit: data.product.unit_of_measure });
    setAdded(true);
    setTimeout(() => setAdded(false), 2200);
  }

  const savings     = data ? data.most_expensive_price - data.cheapest_price : 0;
  const savingsPct  = data ? Math.round((savings / data.most_expensive_price) * 100) : 0;
  const avgPrice    = data
    ? data.prices.reduce((s, p) => s + p.price, 0) / data.prices.length
    : 0;

  return (
    <div className="page-wrapper">
      <div className="container">

        {/* Back */}
        <button className="page-back" onClick={() => navigate(-1)}>
          <ArrowRight size={18} strokeWidth={2} style={{ transform: 'scaleX(-1)' }} />
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
                {/* Image placeholder */}
                <div className="product-image-placeholder">
                  <Barcode size={28} strokeWidth={1.3} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <h1 className="product-hero-name">{data.product.name}</h1>
                  <div className="product-hero-meta" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px' }}>
                    {data.product.brand && <span>{data.product.brand}</span>}
                    {data.product.manufacturer && data.product.manufacturer !== data.product.brand && (
                      <span>{data.product.manufacturer}</span>
                    )}
                    {data.product.category && <span>{data.product.category}</span>}
                    {data.product.unit_of_measure && <span>{data.product.unit_of_measure}</span>}
                    {data.product.barcode && (
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--ink-300)' }}>
                        <Barcode size={11} strokeWidth={2} style={{ display: 'inline', verticalAlign: 'middle', marginInlineEnd: 3 }} />
                        {data.product.barcode}
                      </span>
                    )}
                  </div>
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

              {/* Savings callout */}
              {savings > 0.01 && (
                <div className="product-hero-savings savings-pop">
                  <TrendingDown size={16} strokeWidth={2} />
                  <span>
                    חסוך עד{' '}
                    <strong className="tabular">{fmt(savings)}</strong>
                    {savingsPct > 0 && <span style={{ marginInlineStart: 4, opacity: 0.8 }}>({savingsPct}%)</span>}
                    {' '}בין הרשתות
                  </span>
                </div>
              )}
            </div>

            {/* ── Quick stats ────────────────────────────────── */}
            <div className="stats-bar">
              <div className="stat-item highlight">
                <div className="stat-label">הכי זול</div>
                <div className="stat-value">{fmt(data.cheapest_price)}</div>
                <div className="stat-sub">{data.prices[0]?.chain_name}</div>
              </div>
              <div className="stat-item">
                <div className="stat-label">ממוצע</div>
                <div className="stat-value">{fmt(avgPrice)}</div>
                <div className="stat-sub">{data.prices.length} חנויות</div>
              </div>
              <div className="stat-item savings">
                <div className="stat-label">חסכון</div>
                <div className="stat-value">{fmt(savings)}</div>
                <div className="stat-sub">{savingsPct}%</div>
              </div>
            </div>

            {/* ── Compare table ──────────────────────────────── */}
            <div className="section-header">
              <div>
                <div className="section-title">
                  {data.prices.length} חנויות · מחיר נוכחי
                </div>
                <div className="section-subtitle">ממוין מהזול ליקר</div>
              </div>
            </div>

            <div className="compare-table" style={{ marginBottom: 20 }}>
              {data.prices.map((row, idx) => {
                const isCheapest = idx === 0;
                const diff = row.price - data.cheapest_price;
                return (
                  <div
                    key={`${row.store_id}-${idx}`}
                    className={`compare-row${isCheapest ? ' cheapest' : ''}`}
                  >
                    <span className="compare-row-rank">{idx + 1}</span>

                    <ChainLogo name={row.chain_name} size={44} />

                    <div className="compare-row-info">
                      <div className="compare-row-store">{row.store_name}</div>
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
    </div>
  );
}
