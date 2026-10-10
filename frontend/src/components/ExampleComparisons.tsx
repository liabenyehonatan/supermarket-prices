import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchExamples, type ExampleComparison } from '../api/client';
import { ProductImage } from './ProductImage';
import { ChainLogo } from './ChainLogo';
import { extractProductDisplay } from '../lib/utils';

const money = (p: number | string) => `₪${Number(p).toFixed(2)}`;

/** Real products with a real price gap, so a first-time visitor sees what the app is for. */
export function ExampleComparisons() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ExampleComparison[]>([]);
  useEffect(() => { fetchExamples(5).then(setItems).catch(() => {}); }, []);
  if (!items.length) return null;

  const avgPct = Math.round(
    items.reduce((sum, x) => sum + (Number(x.priciest_price) - Number(x.cheapest_price)) / Number(x.priciest_price), 0)
      / items.length * 100,
  );

  return (
    <>
      <div className="section-header home-section-head">
        <div>
          <div className="section-title">כמה אפשר לחסוך</div>
          <div className="section-subtitle">
            {avgPct > 0 ? `בממוצע ${avgPct}% פחות ברשת הזולה · מחירים אמיתיים מהסניפים` : 'מחירים אמיתיים מהסניפים שלנו'}
          </div>
        </div>
      </div>
      <div className="card-row example-carousel">
        {items.map(x => {
          const lo = Number(x.cheapest_price);
          const hi = Number(x.priciest_price);
          const pct = hi > 0 ? Math.round(((hi - lo) / hi) * 100) : 0;
          const sameChain = x.cheapest_chain === x.priciest_chain;
          const { displayName } = extractProductDisplay(x.name, x.brand, x.unit_of_measure);
          return (
            <button key={x.barcode} className="example-card" onClick={() => navigate(`/product/${x.barcode}`)}>
              <span className="example-card-top">
                <ProductImage barcode={x.barcode} name={x.name} size={36} />
                <span className="example-name">{displayName}</span>
              </span>
              <span className="example-save-row">
                <span className="example-save-amount">חוסכים <bdi dir="ltr">{money(hi - lo)}</bdi></span>
                {pct > 0 && <span className="example-save-pct"><bdi dir="ltr">{pct}%</bdi></span>}
              </span>
              <span className="example-prices-row">
                <span className="example-chain-row is-cheap">
                  {sameChain ? <span className="example-chain-name">זול</span> : <ChainLogo name={x.cheapest_chain} size={20} />}
                  <bdi dir="ltr" className="example-chain-price">{money(lo)}</bdi>
                </span>
                <span className="example-chain-row is-pricey">
                  {sameChain ? <span className="example-chain-name">יקר</span> : <ChainLogo name={x.priciest_chain} size={20} />}
                  <bdi dir="ltr" className="example-chain-price">{money(hi)}</bdi>
                </span>
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}
