import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchDeals, type Deal } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { onCityFilterChange, readCityFilter } from '../lib/filters';
import { DealCard } from './DealCard';
import { DealProductsSheet } from './DealProductsSheet';

/** The home-page strip: a few of the best promotions, two per brand at most. Absent when there are none. */
export function DealsStrip({ chain }: { chain: string }) {
  const { addItem } = useBasket();
  const [city, setCity] = useState(readCityFilter);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [picking, setPicking] = useState<Deal | null>(null);

  useEffect(() => onCityFilterChange(setCity), []);
  useEffect(() => {
    let live = true;
    fetchDeals({ chain, city, diverse: true, limit: 8 })
      .then(r => { if (live) setDeals(r.deals); })
      .catch(() => { if (live) setDeals([]); });
    return () => { live = false; };
  }, [chain, city]);

  if (deals.length === 0) return null;
  return (
    <>
      <div className="section-header home-section-head">
        <div>
          <div className="section-title">מבצעים</div>
          <div className="section-subtitle">רק מבצעים שבאמת זולים מהמחיר שמצאנו ברשתות</div>
        </div>
        <Link className="deals-all-link" to="/promotions">כל המבצעים</Link>
      </div>
      <div className="deals-strip">
        {deals.map(d => (
          <DealCard key={d.deal_id} deal={d} onPick={setPicking}
            onAdd={deal => deal.sample_products[0] && addItem({
              barcode: deal.sample_products[0].barcode, name: deal.sample_products[0].name, brand: deal.sample_products[0].brand,
              unit: deal.sample_products[0].unit_of_measure, quantity: deal.min_qty })} />
        ))}
      </div>
      {picking && <DealProductsSheet deal={picking} onClose={() => setPicking(null)} />}
    </>
  );
}
