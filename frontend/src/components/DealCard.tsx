import { Link } from 'react-router-dom';
import { ShoppingBasket } from 'lucide-react';
import type { Deal } from '../api/client';
import { ChainLogo } from './ChainLogo';
import { ProductImage } from './ProductImage';
import { endsText } from '../lib/dealDays';

const money = (p: number | string) => `₪${Number(p).toFixed(2)}`;

/** One promotion at one brand: the set price, what a unit costs, and how far under the cheapest shelf price it is. */
export function DealCard({ deal, onAdd, onPick }: { deal: Deal; onAdd: (deal: Deal) => void; onPick: (deal: Deal) => void }) {
  const pct = Math.round(Number(deal.saving_pct) * 100);
  const ends = endsText(deal.ends_at);
  const first = deal.sample_products[0];
  // Only real pictures: a row of identical placeholder baskets says nothing and crowds the card
  const pictured = deal.sample_products.filter(p => p.image_url).slice(0, deal.kind === 'group' ? 3 : 1);
  return (
    <article className="deal-card">
      <div className="deal-card-head">
        <ChainLogo name={deal.brand} size={28} />
        <span className="deal-card-brand">{deal.brand}</span>
      </div>

      <div className="deal-card-body">
        {pictured.length > 0 && (
          <div className="deal-card-pics">
            {pictured.map(p => (
              <ProductImage key={p.barcode} barcode={p.barcode} name={p.name} imageUrl={p.image_url} size={deal.kind === 'group' ? 48 : 72} />
            ))}
          </div>
        )}
        <div className="deal-card-main">
          {/* The whole card opens the product (or, for a group, the picker): the title carries the link and stretches over the card */}
          <div className="deal-card-title">
            {deal.kind === 'single' && first
              ? <Link className="deal-card-link" to={`/product/${first.barcode}`}>{first.name}</Link>
              : <button type="button" className="deal-card-link" onClick={() => onPick(deal)}>{first?.name ?? deal.description}</button>}
          </div>
          {deal.kind === 'group' && (
            <div className="deal-card-more">{deal.products === 2 ? 'ועוד מוצר אחד לבחירה במבצע' : `ועוד ${deal.products - 1} מוצרים לבחירה במבצע`}</div>
          )}
          <div className="deal-card-offer-row">
            {/* "1 for ₪9" reads oddly: a one-unit promotion is just the price */}
            <span className="deal-card-offer tabular">
              {deal.min_qty === 1 ? <bdi>{money(deal.price)}</bdi> : <><bdi>{deal.min_qty}</bdi> ב-<bdi>{money(deal.price)}</bdi></>}
            </span>
            <span className="deal-saving-pill tabular" aria-label={`זול ב-${pct}%`}><bdi dir="ltr">-{pct}%</bdi></span>
          </div>
          {deal.min_qty > 1 && <div className="deal-card-unit tabular"><bdi>{money(deal.unit_price)}</bdi> ליחידה</div>}
        </div>
      </div>

      <div className="deal-card-saving">
        {deal.vs_market
          ? <>הזול ביותר שמצאנו: <bdi>{money(deal.ref_price)}</bdi> ליחידה</>
          : <>על המדף ברשת: <bdi>{money(deal.ref_price)}</bdi> ליחידה</>}
      </div>
      {deal.max_qty ? <div className="deal-card-note">המבצע עד {deal.max_qty} יחידות</div> : null}
      {ends && <div className="deal-card-ends">{ends}</div>}

      <div className="deal-card-actions">
        {deal.kind === 'single' && first ? (
          <button className="btn btn-primary btn-sm" onClick={() => onAdd(deal)}>
            <ShoppingBasket size={14} strokeWidth={2} /> הוסיפי לסל (×{deal.min_qty})
          </button>
        ) : (
          <button className="btn btn-primary btn-sm" onClick={() => onPick(deal)}>בחרי מוצרים</button>
        )}
      </div>
    </article>
  );
}
