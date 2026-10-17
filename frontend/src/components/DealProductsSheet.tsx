import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, Plus, X } from 'lucide-react';
import { fetchDealProducts, type Deal, type DealProduct } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { useFocusTrap } from '../lib/useFocusTrap';
import { ProductImage } from './ProductImage';
import { flyToBasket } from '../lib/flyToBasket';

/** The products a group promotion covers: add any, the basket prices "any N of these" itself. */
export function DealProductsSheet({ deal, onClose }: { deal: Deal; onClose: () => void }) {
  const trapRef = useFocusTrap();
  const { addItem } = useBasket();
  const [products, setProducts] = useState<DealProduct[] | null>(null);
  const [added, setAdded] = useState<Set<string>>(new Set());

  useEffect(() => { fetchDealProducts(deal.deal_id).then(setProducts).catch(() => setProducts([])); }, [deal.deal_id]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  function add(p: DealProduct, row: Element | null) {
    addItem({ barcode: p.barcode, name: p.name, brand: p.brand, unit: p.unit_of_measure, quantity: 1 }, () => flyToBasket(row));
    setAdded(prev => new Set(prev).add(p.barcode));
  }

  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="location-sheet filter-sheet" role="dialog" aria-modal="true" tabIndex={-1} ref={trapRef}
           aria-label="מוצרי המבצע" onClick={e => e.stopPropagation()}>
        <div className="sheet-grab"><div className="sheet-handle" /></div>
        <div className="location-sheet-head">
          <strong>{deal.min_qty} ב-₪{Number(deal.price).toFixed(2)} · {deal.brand}</strong>
          <button className="location-sheet-close" onClick={onClose} aria-label="סגירה"><X size={20} /></button>
        </div>
        <div className="deal-sheet-hint">הוסיפי {deal.min_qty} מוצרים כלשהם מהרשימה, ובסל נחשב להם את מחיר המבצע.</div>
        <div className="deal-sheet-list">
          {products === null && <div className="deal-sheet-hint">טוענים…</div>}
          {products?.map(p => (
            <div key={p.barcode} className="deal-sheet-row">
              <ProductImage barcode={p.barcode} name={p.name} imageUrl={p.image_url} size={40} />
              <div className="deal-sheet-name">{p.name}</div>
              <button className="btn btn-secondary btn-sm" onClick={e => add(p, e.currentTarget.closest('.deal-sheet-row'))} aria-label={`הוסיפי ${p.name} לסל`}>
                {added.has(p.barcode) ? <Check size={14} strokeWidth={2.5} /> : <Plus size={14} strokeWidth={2.5} />}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
