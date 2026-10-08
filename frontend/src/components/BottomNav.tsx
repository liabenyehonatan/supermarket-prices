import { NavLink } from 'react-router-dom';
import { Home, ScanLine, ShoppingBasket } from 'lucide-react';
import { useBasket } from '../context/BasketContext';

export function BottomNav() {
  const { totalItems } = useBasket();

  return (
    <nav className="bottom-nav" aria-label="ניווט ראשי">
      <NavLink
        to="/"
        end
        className={({ isActive }) => `bottom-nav-item${isActive ? ' active' : ''}`}
        aria-label="דף הבית"
      >
        <Home size={22} strokeWidth={1.8} />
        <span className="bottom-nav-item-label">בית</span>
      </NavLink>

      <NavLink to="/scan" className="bottom-nav-scan" aria-label="סריקת ברקוד">
        <span className="bottom-nav-scan-btn"><ScanLine size={26} strokeWidth={2} /></span>
        <span className="bottom-nav-item-label">סריקה</span>
      </NavLink>

      <NavLink
        to="/basket"
        className={({ isActive }) => `bottom-nav-item${isActive ? ' active' : ''}`}
        aria-label={`סל קניות — ${totalItems} פריטים`}
        style={{ position: 'relative' }}
      >
        <div style={{ position: 'relative' }}>
          <ShoppingBasket size={22} strokeWidth={1.8} />
          {totalItems > 0 && (
            <span
              className="basket-count"
              style={{ top: -6, insetInlineEnd: -8 }}
              aria-hidden="true"
            >
              {totalItems > 99 ? '99+' : totalItems}
            </span>
          )}
        </div>
        <span className="bottom-nav-item-label">סל</span>
      </NavLink>
    </nav>
  );
}
