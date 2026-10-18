import { Link } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { Deal } from '../api/client';
import { ChainLogo } from './ChainLogo';
import { ProductImage } from './ProductImage';
import { endsText } from '../lib/dealDays';
import { flyToBasket } from '../lib/flyToBasket';

const money = (p: number | string) => `₪${Number(p).toFixed(2)}`;

/**
 * One promotion at one brand, drawn like a product card: the picture, the set price with the add button beside it,
 * the name, then which brand it is and how far under the cheapest shelf price it is.
 */
export function DealCard({ deal, onAdd, onPick }: {
  deal: Deal;
  /** `onAdded` runs once the item is in a basket (it starts the "thrown into the basket" animation) */
  onAdd: (deal: Deal, onAdded: () => void) => void;
  onPick: (deal: Deal) => void;
}) {
  const pct = Math.round(Number(deal.saving_pct) * 100);
  const ends = endsText(deal.ends_at);
  const first = deal.sample_products[0];
  const mediaRef = useRef<HTMLDivElement>(null);
  const [justAdded, setJustAdded] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  // Only real pictures in a group (a row of identical placeholder baskets crowds the card); one placeholder if there are none
  const pictured = deal.sample_products.filter(p => p.image_url).slice(0, deal.kind === 'group' ? 3 : 1);
  const single = deal.kind === 'single' && first;
  return (
    <article className="deal-card">
      <div className="deal-card-media" ref={mediaRef}>
        <span className="deal-saving-pill tabular" aria-label={`זול ב-${pct}%`}><bdi dir="ltr">-{pct}%</bdi></span>
        {/* A blank box looks like a picture that did not load: without one, the same placeholder as everywhere else */}
        <div className={`deal-card-pics${pictured.length > 1 ? ' is-group' : ''}`}>
          {pictured.length > 0
            ? pictured.map(p => (
                <ProductImage key={p.barcode} barcode={p.barcode} name={p.name} imageUrl={p.image_url} size={pictured.length > 1 ? 52 : '100%'} borderRadius={0} />
              ))
            : <ProductImage barcode={first?.barcode ?? ''} name={first?.name ?? deal.description} noPicture size="100%" borderRadius={0} />}
        </div>
      </div>

      <div className="deal-card-body">
        {/* "1 for ₪9" reads oddly: a one-unit promotion is just the price */}
        <div className="deal-card-offer-row">
          <span className="deal-card-offer tabular">
            {deal.min_qty === 1 ? <bdi>{money(deal.price)}</bdi> : <><bdi>{deal.min_qty}</bdi> ב-<bdi>{money(deal.price)}</bdi></>}
          </span>
          {deal.min_qty > 1 && <span className="deal-card-unit tabular"><bdi>{money(deal.unit_price)}</bdi> ליחידה</span>}
        </div>

        {/* The whole card opens the product (or, for a group, the picker): the title carries the link and stretches over the card */}
        <div className="deal-card-title">
          {single
            ? <Link className="deal-card-link" to={`/product/${first.barcode}`} title={first.name}>{first.name}</Link>
            : <button type="button" className="deal-card-link" onClick={() => onPick(deal)} title={first?.name ?? deal.description}
                tabIndex={-1} aria-hidden="true">{first?.name ?? deal.description}</button>   /* keyboard and screen readers use the "בחירה" button */}
        </div>
        {/* Always one line, empty for a single product, so the rows below sit at the same height on every card */}
        <div className="deal-card-more" aria-hidden={deal.kind !== 'group' || undefined}>
          {deal.kind === 'group'
            ? (deal.products === 2 ? 'ועוד מוצר אחד לבחירה' : `ועוד ${deal.products - 1} מוצרים לבחירה`)
            : '\u00a0'}
        </div>

        <div className="deal-card-where">
          <ChainLogo name={deal.brand} size={16} />
          <span className="deal-card-brand">{deal.brand}</span>
        </div>
        {/* Room for all three lines on every card (the last two are not always there) */}
        <div className="deal-card-meta">
          <div className="deal-card-saving">
            {deal.vs_market
              ? <>הזול ביותר שמצאנו: <bdi>{money(deal.ref_price)}</bdi></>
              : <>על המדף ברשת: <bdi>{money(deal.ref_price)}</bdi></>}
          </div>
          {deal.max_qty ? <div className="deal-card-note">המבצע עד {deal.max_qty} יחידות</div> : null}
          {ends && <div className="deal-card-ends">{ends}</div>}
        </div>

        {single ? (
          <button
            type="button"
            className={`card-add${justAdded ? ' is-added' : ''}`}
            aria-label={`הוספה לסל: ${first.name}${deal.min_qty > 1 ? ` (×${deal.min_qty})` : ''}`}
            onClick={() => onAdd(deal, () => {
              flyToBasket(mediaRef.current);
              setJustAdded(true);
              if (timer.current) clearTimeout(timer.current);
              timer.current = setTimeout(() => setJustAdded(false), 1200);
            })}
          >
            {justAdded ? <><Check size={15} strokeWidth={2.6} /> נוסף</> : <><Plus size={15} strokeWidth={2.6} /> {deal.min_qty > 1 ? `הוספה (×${deal.min_qty})` : 'הוספה'}</>}
          </button>
        ) : (
          <button type="button" className="card-add" onClick={() => onPick(deal)} aria-label="בחירת מוצרים מהמבצע">בחירת מוצרים</button>
        )}
      </div>
    </article>
  );
}
