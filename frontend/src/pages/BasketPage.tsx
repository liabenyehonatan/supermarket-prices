import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ShoppingBasket, Search, Minus, Plus, Trash2,
  ChevronDown, ChevronUp, TrendingUp, AlertCircle,
  Tag, Truck, CheckCircle2, ExternalLink, Navigation, MapPin,
} from 'lucide-react';
import { compareBasket } from '../api/client';
import { ChainLogo } from '../components/ChainLogo';
import { ProductImage } from '../components/ProductImage';
import { useBasket } from '../context/BasketContext';
import type { BasketCompareResponse, BasketStoreTotal } from '../types';

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
  const [open, setOpen] = useState(rank === 0);
  const isWinner  = rank === 0;
  const savings   = maxTotal - store.total_price;
  const savingsPct = maxTotal > 0 ? Math.round((savings / maxTotal) * 100) : 0;

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

      <div className="basket-result-header">
        <div style={{ position: 'relative' }}>
          <ChainLogo name={store.store.chain.name} size={52} />
          {isWinner && (
            <span
              style={{
                position: 'absolute', top: -6, insetInlineEnd: -6,
                background: 'var(--green-600)', color: '#fff',
                borderRadius: '50%', width: 20, height: 20,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
              aria-label="הכי זול"
            >
              <Tag size={11} strokeWidth={2.5} />
            </span>
          )}
        </div>

        <div className="basket-result-chain">
          <div className="basket-result-chain-name">{store.store.chain.name}</div>
          <div className="basket-result-store-info">
            {[store.store.name, store.store.city].filter(Boolean).join(' · ')}
          </div>
          <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
            {isWinner && (
              <span className="badge badge-cheapest" style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Tag size={10} strokeWidth={2.5} />
                הכי זול
              </span>
            )}
            {store.store.delivery_url && (
              <a
                href={store.store.delivery_url}
                target="_blank"
                rel="noopener noreferrer"
                className="compare-row-delivery"
                onClick={e => e.stopPropagation()}
              >
                <Truck size={10} strokeWidth={2} />
                משלוח
                <ExternalLink size={9} strokeWidth={2} />
              </a>
            )}
            {store.items_missing > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 12, color: 'var(--red-500)' }}>
                <AlertCircle size={12} strokeWidth={2} />
                {store.items_missing} חסר
              </span>
            )}
          </div>
          <div className="compare-row-nav">
            <a
              href={wazeUrl(store.store)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              aria-label={`נווט בוויז ל-${store.store.name}`}
            >
              <Navigation size={10} strokeWidth={2} />
              Waze
            </a>
            <a
              href={googleMapsUrl(store.store)}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              aria-label={`נווט בגוגל מפות ל-${store.store.name}`}
            >
              <MapPin size={10} strokeWidth={2} />
              Maps
            </a>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <div className="basket-result-total tabular">{fmt(store.total_price)}</div>
          {!isWinner && store.total_price - minTotal > 0.01 && (
            <span style={{ fontSize: 12, color: 'var(--red-500)', fontWeight: 600 }} className="tabular">
              +{fmt(store.total_price - minTotal)}
            </span>
          )}
          {rank === 1 && (
            <span className="badge badge-neutral" style={{ fontSize: 11 }}>מקום 2</span>
          )}
        </div>
      </div>

      {/* Expand/collapse */}
      <button
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          gap: 6, padding: '10px 20px', border: 'none',
          borderTop: '1px solid var(--line)', background: 'transparent',
          color: 'var(--ink-500)', fontSize: 13, fontWeight: 500,
          cursor: 'pointer', fontFamily: 'var(--font-sans)',
        }}
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
      >
        {open
          ? <><ChevronUp size={15} strokeWidth={2} /> הסתר פירוט</>
          : <><ChevronDown size={15} strokeWidth={2} /> פירוט פריטים ({store.item_prices.filter(i => !i.missing).length}/{store.item_prices.length})</>
        }
      </button>

      {open && (
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
      )}
    </div>
  );
}

/* ── Main page ───────────────────────────────────────────── */
export function BasketPage() {
  const navigate = useNavigate();
  const { items, updateQty, removeItem, clearBasket } = useBasket();
  const [results, setResults] = useState<BasketCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  async function handleCompare() {
    if (!items.length) return;
    setLoading(true); setError(null); setResults(null);
    try {
      const data = await compareBasket(items.map(i => ({ barcode: i.barcode, quantity: i.quantity })));
      setResults(data);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);
    } catch {
      setError('לא הצלחנו להשוות. בדוק שהשרת פעיל ונסה שוב.');
    } finally {
      setLoading(false);
    }
  }

  const completeStores = results ? results.stores.filter(s => s.items_missing === 0) : [];
  const maxTotal = completeStores.length >= 2
    ? Math.max(...completeStores.map(s => s.total_price))
    : results ? Math.max(...results.stores.map(s => s.total_price)) : 0;
  const minTotal = results && results.stores.length > 0 ? results.stores[0].total_price : 0;
  const totalItems = items.reduce((s, i) => s + i.quantity, 0);

  /* Empty state */
  if (!items.length && !results) {
    return (
      <div className="page-wrapper">
        <div className="container">
          <div className="empty-state" style={{ paddingTop: 64 }}>
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
      <div className="container">

        {/* Header */}
        <div className="section-header" style={{ marginBottom: 20 }}>
          <div>
            <h1 style={{ fontSize: 'var(--fs-24)', fontWeight: 700, color: 'var(--ink-900)', letterSpacing: '-0.01em' }}>
              הסל שלי
            </h1>
            <div className="section-subtitle">
              {items.length} מוצר{items.length !== 1 ? 'ים' : ''} · {totalItems} יח׳ בסך הכל
            </div>
          </div>
          {items.length > 0 && (
            <button
              className="btn btn-ghost btn-sm"
              style={{ color: 'var(--red-500)' }}
              onClick={() => { setResults(null); clearBasket(); }}
            >
              <Trash2 size={15} strokeWidth={1.8} />
              נקה סל
            </button>
          )}
        </div>

        {/* Item list */}
        {items.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
            {items.map(item => (
              <div key={item.barcode} className="basket-item">
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
                <div className="basket-item-controls">
                  <button
                    className="qty-btn"
                    onClick={() => item.quantity <= 1 ? removeItem(item.barcode) : updateQty(item.barcode, item.quantity - 1)}
                    aria-label="הפחת כמות"
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
              </div>
            ))}
          </div>
        )}

        {/* Add more */}
        <button
          className="btn btn-secondary btn-full"
          style={{ marginBottom: 12 }}
          onClick={() => navigate('/')}
        >
          <Search size={17} strokeWidth={2} />
          הוסף מוצרים לסל
        </button>

        {/* Compare CTA */}
        {items.length > 0 && (
          <button
            className="btn btn-primary btn-compare btn-lg btn-full"
            style={{ marginBottom: 32 }}
            onClick={handleCompare}
            disabled={loading}
          >
            {loading
              ? 'משווה מחירים...'
              : <>
                  <CartPercentIcon />
                  השווה מחירים עבור {totalItems} פריטים
                </>
            }
          </button>
        )}

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

            <div className="section-header" style={{ marginBottom: 16 }}>
              <div>
                <div className="section-title" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <TrendingUp size={20} strokeWidth={2} color="var(--green-600)" />
                  {results.stores.length} רשתות · ממוין מהזול ליקר
                </div>
                <div className="section-subtitle">
                  עבור {results.total_items_requested} מוצרים בסל
                </div>
              </div>
            </div>

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
    </div>
  );
}
