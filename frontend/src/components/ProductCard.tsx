import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Check, Plus } from 'lucide-react';
import { ProductImage } from './ProductImage';
import { useBasket } from '../context/BasketContext';
import { cleanBrand, extractProductDisplay } from '../lib/utils';
import { money } from '../lib/safe';
import { flyToBasket } from '../lib/flyToBasket';
import type { Product } from '../types';

/**
 * One search result as a card: picture on top, name (two lines), size and brand, the cheapest price, and an add button
 * on the picture. The whole card opens the product; the add button only adds. When the product is already in the
 * active basket the button shows how many, so a shopper can see what is in the basket without opening it.
 */
export function ProductCard({ product, price }: { product: Product; price: number | undefined }) {
  const navigate = useNavigate();
  const { addItem, items } = useBasket();
  const [justAdded, setJustAdded] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const inBasket = items.find(i => i.barcode === product.barcode)?.quantity ?? 0;
  const { displayName, size, tailBrand } = extractProductDisplay(product.name, product.brand, product.unit_of_measure);
  const brand = [tailBrand || cleanBrand(product.brand)].find(s => s && s !== '---') ?? '';
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
      <button
        type="button"
        className={`result-card-add${justAdded ? ' is-added' : ''}${inBasket ? ' in-basket' : ''}`}
        onClick={add}
        aria-label={inBasket ? `${product.name}: ${inBasket} בסל. הוספת עוד אחד` : `הוספת ${product.name} לסל`}
      >
        {justAdded
          ? <Check size={14} strokeWidth={2.5} />
          : inBasket ? <span className="tabular">{inBasket}</span> : <Plus size={14} strokeWidth={2.5} />}
      </button>

      <div className="result-card-body">
        {/* The name is the link (keyboard, screen readers, open in a new tab); the card's own click covers the rest */}
        <a
          className="result-card-name"
          href={`#/product/${product.barcode}`}
          onClick={e => { e.preventDefault(); e.stopPropagation(); open(); }}
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
        <div className="result-card-price">
          {price != null ? (
            <>
              <span className="result-card-price-label">הכי זול</span>
              <span className="result-card-price-value tabular" dir="ltr">{money(price)}</span>
            </>
          ) : (
            <span className="skeleton" style={{ width: 72, height: 22, display: 'block' }} />
          )}
        </div>
      </div>
    </article>
  );
}

/** Placeholder with the card's exact shape, so the grid does not move when the real card arrives. */
export function ProductCardSkeleton() {
  return (
    <div className="result-card is-skeleton" aria-hidden>
      <div className="result-card-media"><div className="skeleton" style={{ width: '100%', height: '100%', borderRadius: 0 }} /></div>
      <div className="result-card-body">
        <div className="skeleton" style={{ height: 14, width: '90%' }} />
        <div className="skeleton" style={{ height: 14, width: '60%', marginTop: 6 }} />
        <div className="skeleton" style={{ height: 22, width: 72, marginTop: 'auto' }} />
      </div>
    </div>
  );
}
