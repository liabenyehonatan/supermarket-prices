import { Link } from 'react-router-dom';
import { ShoppingBasket } from 'lucide-react';
import type { Deal } from '../api/client';
import { ChainLogo } from './ChainLogo';
import { ProductImage } from './ProductImage';
import { daysLeft } from '../lib/dealDays';

const money = (p: number | string) => `₪${Number(p).toFixed(2)}`;

function endsText(iso?: string | null): string | null {
  if (!iso) return null;
  const days = daysLeft(iso);
  if (days <= 0) return 'נגמר היום';
  if (days === 1) return 'נגמר מחר';
  return days <= 14 ? `נגמר בעוד ${days} ימים` : null;
}

/** One promotion at one brand: the set price, what a unit costs, and how far under the cheapest shelf price it is. */
export function DealCard({ deal, onAdd, onPick }: { deal: Deal; onAdd: (deal: Deal) => void; onPick: (deal: Deal) => void }) {
  const pct = Math.round(Number(deal.saving_pct) * 100);
  const ends = endsText(deal.ends_at);
  const first = deal.sample_products[0];
  return (
    <article className="deal-card">
      <div className="deal-card-head">
        <ChainLogo name={deal.brand} size={28} />
        <span className="deal-card-brand">{deal.brand}</span>
        <span className="deal-card-stores">{deal.stores === 1 ? 'בסניף אחד' : `ב-${deal.stores} סניפים`}</span>
      </div>

      <div className="deal-card-body">
        <div className="deal-card-pics">
          {deal.sample_products.slice(0, deal.kind === 'group' ? 3 : 1).map(p => (
            <ProductImage key={p.barcode} barcode={p.barcode} name={p.name} imageUrl={p.image_url} size={deal.kind === 'group' ? 48 : 72} />
          ))}
        </div>
        <div className="deal-card-main">
          <div className="deal-card-title" title={deal.description}>
            {deal.kind === 'group' ? `${deal.products} מוצרים לבחירה` : first?.name ?? deal.description}
          </div>
          <div className="deal-card-offer tabular"><bdi>{deal.min_qty}</bdi> ב-<bdi>{money(deal.price)}</bdi></div>
          <div className="deal-card-unit tabular"><bdi>{money(deal.unit_price)}</bdi> ליחידה</div>
        </div>
      </div>

      <div className="deal-card-saving">
        {deal.vs_market
          ? <>זול ב-<bdi>{pct}%</bdi> מהמחיר הזול שמצאנו ברשתות (<bdi>{money(deal.ref_price)}</bdi> ליחידה)</>
          : <>זול ב-<bdi>{pct}%</bdi> ממחיר המדף ברשת (<bdi>{money(deal.ref_price)}</bdi> ליחידה)</>}
      </div>
      {deal.max_qty ? <div className="deal-card-note">המבצע עד {deal.max_qty} יחידות</div> : null}
      {ends && <div className="deal-card-ends">{ends}</div>}

      <div className="deal-card-actions">
        {deal.kind === 'single' && first ? (
          <>
            <button className="btn btn-primary btn-sm" onClick={() => onAdd(deal)}>
              <ShoppingBasket size={14} strokeWidth={2} /> הוסיפי לסל (×{deal.min_qty})
            </button>
            <Link className="btn btn-secondary btn-sm" to={`/product/${first.barcode}`}>איפה הכי זול</Link>
          </>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => onPick(deal)}>בחרי מוצרים</button>
        )}
      </div>
    </article>
  );
}
