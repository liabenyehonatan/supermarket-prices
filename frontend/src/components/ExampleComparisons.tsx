import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchExamples, type ExampleComparison } from '../api/client';
import { ProductImage } from './ProductImage';
import { extractProductDisplay } from '../lib/utils';

const money = (p: number | string) => `₪${Number(p).toFixed(2)}`;

/** Real products with a real price gap, so a first-time visitor sees what the app is for. */
export function ExampleComparisons() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ExampleComparison[]>([]);
  useEffect(() => { fetchExamples(3).then(setItems).catch(() => {}); }, []);
  if (!items.length) return null;

  return (
    <>
      <div className="section-header" style={{ marginBottom: 12 }}>
        <div>
          <div className="section-title">כמה אפשר לחסוך</div>
          <div className="section-subtitle">מחירים אמיתיים מהסניפים שלנו</div>
        </div>
      </div>
      <div className="example-list">
        {items.map(x => {
          const lo = Number(x.cheapest_price);
          const hi = Number(x.priciest_price);
          const { displayName } = extractProductDisplay(x.name, x.brand, x.unit_of_measure);
          const where = x.cheapest_chain !== x.priciest_chain
            ? `${x.cheapest_chain} הכי זול · ${x.priciest_chain} הכי יקר`
            : `בין ${x.stores_count} סניפים`;
          return (
            <button key={x.barcode} className="example-row" onClick={() => navigate(`/product/${x.barcode}`)}>
              <ProductImage barcode={x.barcode} name={x.name} size={48} />
              <span className="example-text">
                <span className="example-name">{displayName}</span>
                <span className="example-where">{where}</span>
              </span>
              <span className="example-prices">
                <span className="example-range"><bdi dir="ltr">{money(lo)} – {money(hi)}</bdi></span>
                <span className="example-save">חיסכון עד {money(hi - lo)}</span>
              </span>
            </button>
          );
        })}
      </div>
    </>
  );
}
