import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchExamples, compareProduct, type ExampleComparison } from '../api/client';
import { ProductImage } from './ProductImage';
import { ChainLogo } from './ChainLogo';
import { extractProductDisplay } from '../lib/utils';

/** Hand-picked products with good photos; they come first, the automatic picks fill the rest. */
const FEATURED_BARCODES = ['4011800628512', '7290012522581', '7290109352916'];

async function loadFeatured(barcode: string): Promise<ExampleComparison | null> {
  try {
    const r = await compareProduct(barcode);
    const prices = r.prices;
    if (prices.length < 2) return null;
    const lo = prices.reduce((a, b) => (Number(b.price) < Number(a.price) ? b : a));
    const hi = prices.reduce((a, b) => (Number(b.price) > Number(a.price) ? b : a));
    if (Number(hi.price) <= Number(lo.price)) return null;
    return {
      barcode: r.product.barcode, name: r.product.name, brand: r.product.brand, unit_of_measure: r.product.unit_of_measure,
      cheapest_price: lo.price, cheapest_chain: lo.chain_name,
      priciest_price: hi.price, priciest_chain: hi.chain_name, stores_count: prices.length,
    };
  } catch { return null; }
}

const money = (p: number | string) => `₪${Number(p).toFixed(2)}`;

/** Real products with a real price gap, so a first-time visitor sees what the app is for. */
export function ExampleComparisons() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ExampleComparison[]>([]);
  useEffect(() => {
    Promise.all([
      Promise.all(FEATURED_BARCODES.map(loadFeatured)),
      fetchExamples(5).catch(() => [] as ExampleComparison[]),
    ]).then(([featured, auto]) => {
      const picked = featured.filter((x): x is ExampleComparison => !!x);
      const taken = new Set(picked.map(x => x.barcode));
      setItems([...picked, ...auto.filter(x => !taken.has(x.barcode))].slice(0, 5));
    });
  }, []);
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
