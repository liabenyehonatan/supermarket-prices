import { useEffect, useState } from 'react';
import { fetchDeals, type Deal } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { DealCard } from '../components/DealCard';
import { DealProductsSheet } from '../components/DealProductsSheet';
import { onCityFilterChange, readCityFilter } from '../lib/filters';
import { useDocumentTitle } from '../lib/useDocumentTitle';

const PAGE = 24;

export function DealsPage() {
  useDocumentTitle('מבצעים | סלי');
  const { addItem } = useBasket();
  const [city, setCity] = useState(readCityFilter);
  const [chain, setChain] = useState('');
  const [sort, setSort] = useState<'best' | 'ending'>('best');
  const [kind, setKind] = useState<'' | 'single' | 'group'>('');
  const [deals, setDeals] = useState<Deal[]>([]);
  const [total, setTotal] = useState(0);
  const [chains, setChains] = useState<{ name: string; count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [picking, setPicking] = useState<Deal | null>(null);

  useEffect(() => onCityFilterChange(setCity), []);

  useEffect(() => {
    let live = true;
    setLoading(true);
    fetchDeals({ chain, city, sort, kind: kind || undefined, limit: PAGE })
      .then(r => { if (live) { setDeals(r.deals); setTotal(r.total); setChains(r.chains); } })
      .catch(() => { if (live) { setDeals([]); setTotal(0); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [chain, city, sort, kind]);

  async function more() {
    const r = await fetchDeals({ chain, city, sort, kind: kind || undefined, limit: PAGE, offset: deals.length });
    setDeals(prev => [...prev, ...r.deals]);
  }

  const add = (deal: Deal) => deal.sample_products[0] && addItem({
    barcode: deal.sample_products[0].barcode, name: deal.sample_products[0].name, brand: deal.sample_products[0].brand,
    unit: deal.sample_products[0].unit_of_measure, quantity: deal.min_qty,
  });

  return (
    <div className="page-wrapper">
      <div className="container">
        <div className="section-header">
          <div>
            <div className="section-title">מבצעים</div>
            <div className="section-subtitle">
              {total} מבצעים בתוקף{city ? ` בסניפי ${city}` : ''}, מדורגים לפי כמה הם זולים מהמחיר הזול שמצאנו ברשתות
            </div>
          </div>
        </div>

        <div className="filter-bar deals-filters" role="group" aria-label="סינון מבצעים לפי רשת">
          <button className={`filter-chip${chain === '' ? ' active' : ''}`} onClick={() => setChain('')}>כל הרשתות</button>
          {chains.map(c => (
            <button key={c.name} className={`filter-chip${chain === c.name ? ' active' : ''}`} onClick={() => setChain(c.name)}>
              {c.name} · {c.count}
            </button>
          ))}
        </div>
        <div className="filter-bar deals-filters" role="group" aria-label="מיון וסוג">
          <button className={`filter-chip${sort === 'best' ? ' active' : ''}`} onClick={() => setSort('best')}>הכי משתלמים</button>
          <button className={`filter-chip${sort === 'ending' ? ' active' : ''}`} onClick={() => setSort('ending')}>נגמרים בקרוב</button>
          <button className={`filter-chip${kind === 'single' ? ' active' : ''}`} onClick={() => setKind(kind === 'single' ? '' : 'single')}>מוצר בודד</button>
          <button className={`filter-chip${kind === 'group' ? ' active' : ''}`} onClick={() => setKind(kind === 'group' ? '' : 'group')}>קבוצת מוצרים</button>
        </div>

        {!loading && deals.length === 0 && (
          <div className="empty-state" style={{ padding: '32px 0' }}>
            <div className="empty-state-title">אין כרגע מבצעים שמתאימים לסינון</div>
          </div>
        )}
        <div className="deals-grid">
          {deals.map(d => <DealCard key={d.deal_id} deal={d} onPick={setPicking} onAdd={add} />)}
        </div>
        {deals.length < total && (
          <button className="btn btn-secondary btn-full deals-more" onClick={() => void more()}>עוד מבצעים</button>
        )}
        <p className="deals-footnote">
          המחיר ליחידה מחושב מהמבצע. ההשוואה היא למחיר המדף הזול ביותר שמצאנו של אותו מוצר בכל הרשתות. מבצעי מועדון וקופונים לא מוצגים,
          ומוצגים רק מבצעים מרשתות שיש לנו עבורן נתונים עדכניים.
        </p>
      </div>
      {picking && <DealProductsSheet deal={picking} onClose={() => setPicking(null)} />}
    </div>
  );
}
