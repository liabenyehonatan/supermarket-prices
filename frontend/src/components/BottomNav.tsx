import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Home, Search, ScanLine, Percent, ShoppingBasket } from 'lucide-react';
import { useBasket } from '../context/BasketContext';

export function BottomNav() {
  const { totalItems } = useBasket();
  const navigate = useNavigate();
  const { pathname } = useLocation();

  // "Search": the home page with the cursor in its field
  function goSearch() {
    if (pathname !== '/') navigate('/');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    setTimeout(() => document.querySelector<HTMLInputElement>('.search-hero-input')?.focus({ preventScroll: true }), pathname === '/' ? 0 : 350);
  }

  return (
    <nav className="bottom-nav" aria-label="ניווט ראשי">
      <NavLink
        to="/"
        end
        className={({ isActive }) => `bottom-nav-item${isActive ? ' active' : ''}`}
        aria-label="דף הבית"
      >
        <Home size={21} strokeWidth={1.8} />
        <span className="bottom-nav-item-label">בית</span>
      </NavLink>

      <button type="button" className="bottom-nav-item" onClick={goSearch} aria-label="חיפוש מוצר">
        <Search size={21} strokeWidth={1.8} />
        <span className="bottom-nav-item-label">חיפוש</span>
      </button>

      <NavLink to="/scan" className="bottom-nav-scan" aria-label="סריקת ברקוד">
        <span className="bottom-nav-scan-btn"><ScanLine size={24} strokeWidth={2} /></span>
        <span className="bottom-nav-item-label">סריקה</span>
      </NavLink>

      <NavLink
        to="/promotions"
        className={({ isActive }) => `bottom-nav-item${isActive ? ' active' : ''}`}
        aria-label="מבצעים"
      >
        <Percent size={21} strokeWidth={1.8} />
        <span className="bottom-nav-item-label">מבצעים</span>
      </NavLink>

      <NavLink
        to="/basket"
        className={({ isActive }) => `bottom-nav-item${isActive ? ' active' : ''}`}
        aria-label={`סל קניות — ${totalItems} פריטים`}
      >
        <div className="bottom-nav-basket-icon" style={{ position: 'relative' }}>
          <ShoppingBasket size={21} strokeWidth={1.8} />
          {totalItems > 0 && (
            <span className="basket-count" style={{ top: -7, insetInlineEnd: -9 }} aria-hidden="true">
              {totalItems > 99 ? '99+' : totalItems}
            </span>
          )}
        </div>
        <span className="bottom-nav-item-label">סל</span>
      </NavLink>
    </nav>
  );
}
