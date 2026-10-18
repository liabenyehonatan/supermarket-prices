import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import { ProductImage } from './ProductImage';
import { ChainLogo } from './ChainLogo';
import { useBasket } from '../context/BasketContext';
import { extractProductDisplay } from '../lib/utils';
import { brandForCard, sizeUnitPrice, unitPriceLabel } from '../lib/productMeta';
import { money } from '../lib/safe';
import { flyToBasket } from '../lib/flyToBasket';
import type { PriceSummary } from '../api/client';
import type { Product } from '../types';

// Two stacked logos and "הכי זול ב-12 רשתות" still fit one line of a 360px phone's card
const MAX_LOGOS = 2;

/** "הכי זול בשופרסל" with its logo; several brands at the same price: their logos stacked and a count. */
function CheapestWhere({ chains }: { chains: string[] }) {
  if (!chains.length) return null;
  const one = chains.length === 1;
  return (
    <div className="result-card-where" title={chains.join(', ')}>
      <span className="result-card-logos" aria-hidden>
        {chains.slice(0, MAX_LOGOS).map(c => <ChainLogo key={c} name={c} size={16} />)}
      </span>
      <span className="result-card-where-text">הכי זול {one ? `ב${chains[0]}` : `ב-${chains.length} רשתות`}</span>
    </div>
  );
}

/**
 * One search result: picture, name (two lines), size and brand, then where it is cheapest and the price row,
 * with the add button beside the price (it never covers the picture). The whole card opens the product.
 * Once the product is in the active basket the button shows how many, so the list says what is already in.
 */
export function ProductCard({ product, summary }: {
  product: Product;
  /** undefined: still loading; null: no current price */
  summary: PriceSummary | null | undefined;
}) {
  const navigate = useNavigate();
  const { addItem, items } = useBasket();
  const [justAdded, setJustAdded] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const inBasket = items.find(i => i.barcode === product.barcode)?.quantity ?? 0;
  const { displayName, size, tailBrand } = extractProductDisplay(product.name, product.brand, product.unit_of_measure);
  const brand = brandForCard(product.name, tailBrand || product.brand);
  // Worked out from the pack size where it can be read; the chain's own unit price only when it cannot
  const perUnit = summary
    ? sizeUnitPrice(summary.price, product.name, product.brand, product.unit_of_measure) ?? unitPriceLabel(summary.price, summary.unit_price, summary.unit)
    : null;
  const open = () => navigate(`/product/${product.barcode}`);

  function add(e: React.MouseEvent) {
    e.stopPropagation();
    // With several baskets the picker may ask first: the throw waits until the item is really in one
    addItem({ barcode: product.barcode, quantity: 1, name: product.name, brand: product.brand, unit: product.unit_of_measure }, () => {
      flyToBasket(mediaRef.current);
      setJustAdded(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setJustAdded(false), 1200);
    });
  }

  return (
    <article className="result-card" onClick={open}>
      <div className="result-card-media" ref={mediaRef}>
        <ProductImage barcode={product.barcode} name={product.name} imageUrl={product.image_url} size="100%" borderRadius={0} />
      </div>

      <div className="result-card-body">
        {/* The name is the link (keyboard, screen readers, open in a new tab); the card's own click covers the rest */}
        <a
          className="result-card-name"
          href={`/product/${product.barcode}`}
          onClick={e => {
            e.stopPropagation();
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;   // let the browser open it in a new tab
            e.preventDefault();
            open();
          }}
          title={displayName}
        >
          {displayName}
        </a>
        {(size || brand) && (
          <div className="result-card-meta">
            {size && <span className="size-chip">{size}</span>}
            {brand && <span className="result-card-brand">{brand}</span>}
          </div>
        )}

        <div className="result-card-foot">
          {summary === undefined
            ? <span className="skeleton result-card-where" style={{ width: 96, height: 12 }} aria-hidden />
            : summary && <CheapestWhere chains={summary.chains} />}
          {summary === undefined ? (
            <div className="result-card-pricing" aria-hidden>
              <span className="skeleton" style={{ width: 64, height: 20, display: 'block' }} />
            </div>
          ) : summary === null ? (
            <div className="result-card-pricing"><span className="result-card-noprice">אין מחיר עדכני</span></div>
          ) : (
            <div className="result-card-pricing">
              <span className="result-card-price tabular"><bdi dir="ltr">{money(summary.price)}</bdi></span>
              {perUnit && <span className="result-card-unit tabular"><bdi dir="ltr">{perUnit.price}</bdi> {perUnit.per}</span>}
            </div>
          )}
          <button
            type="button"
            className={`card-add${justAdded ? ' is-added' : ''}${inBasket ? ' in-basket' : ''}`}
            onClick={add}
            aria-label={inBasket ? `${product.name}: ${inBasket} בסל. הוספה של עוד אחד` : `הוספה לסל: ${product.name}`}
          >
            {justAdded
              ? <><Check size={15} strokeWidth={2.6} /> נוסף</>
              : inBasket
                ? <><Plus size={15} strokeWidth={2.6} /> <span className="tabular">{inBasket}</span> בסל</>
                : <><Plus size={15} strokeWidth={2.6} /> הוספה</>}
          </button>
        </div>
      </div>
    </article>
  );
}

/** Placeholder with the card's exact shape, so the grid does not move when the real card arrives. */
export function ProductCardSkeleton() {
  return (
    <div className="result-card is-skeleton" aria-hidden>
      <div className="result-card-media"><div className="skeleton" style={{ width: '100%', height: '100%', borderRadius: 10 }} /></div>
      <div className="result-card-body">
        <div className="skeleton" style={{ height: 13, width: '88%' }} />
        <div className="skeleton" style={{ height: 13, width: '56%', marginTop: 6 }} />
        <div className="result-card-foot">
          <span className="skeleton result-card-where" style={{ width: 96, height: 12 }} />
          <span className="skeleton" style={{ width: 64, height: 20, display: 'block' }} />
          <span className="skeleton" style={{ width: '100%', height: 34, borderRadius: 10, display: 'block', marginTop: 10 }} />
        </div>
      </div>
    </div>
  );
}
