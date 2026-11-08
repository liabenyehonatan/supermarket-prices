import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { fetchProductsByBarcodes } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { parseBasketLink } from './basketLink';
import type { LocalBasketItem } from '../types';

export const IMPORTED_BASKET_NAME = 'מקלוד';

/** On the basket page: if the address carries `?items=barcode:qty,...` (the link Claude gives), put those products
 *  in a NEW basket, make it the active one, and take the parameter out of the address so a refresh does not import
 *  again. Existing baskets are never touched. */
export function useBasketLinkImport(): { importing: boolean } {
  const { search, pathname } = useLocation();
  const navigate = useNavigate();
  const { importBasket, notify } = useBasket();
  const [importing, setImporting] = useState(false);
  const handled = useRef(false);   // React's dev double-run of effects must not import twice

  useEffect(() => {
    const params = new URLSearchParams(search);
    if (handled.current || !params.has('items')) return;
    handled.current = true;
    const wanted = parseBasketLink(search);
    params.delete('items');
    const rest = params.toString();
    navigate({ pathname, search: rest ? `?${rest}` : '' }, { replace: true });
    if (!wanted.length) { notify('הקישור לא כולל מוצרים תקינים'); return; }

    setImporting(true);
    fetchProductsByBarcodes(wanted.map(w => w.barcode))
      .then(found => {
        const byBarcode = new Map(found.map(p => [p.barcode, p]));
        const items: LocalBasketItem[] = wanted.flatMap(w => {
          const p = byBarcode.get(w.barcode);
          return p ? [{ barcode: w.barcode, quantity: w.quantity, name: p.name, brand: p.brand, unit: p.unit_of_measure }] : [];
        });
        if (!items.length) notify('לא מצאנו אף אחד מהמוצרים שבקישור');
        else importBasket(IMPORTED_BASKET_NAME, items, wanted.length - items.length);
      })
      .catch(() => notify('לא הצלחנו לפתוח את הסל מהקישור. נסו שוב בעוד רגע'))
      .finally(() => setImporting(false));
  }, [search, pathname, navigate, importBasket, notify]);

  return { importing };
}
