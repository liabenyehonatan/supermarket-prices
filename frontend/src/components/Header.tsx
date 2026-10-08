import { useNavigate, useLocation } from 'react-router-dom';
import { Search, ShoppingBasket } from 'lucide-react';
import { SaliLogo } from './SaliLogo';
import { LocationChip } from './LocationChip';
import { useBasket } from '../context/BasketContext';

export function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const { totalItems } = useBasket();

  const isOnSearch = location.pathname === '/';

  return (
    <header className="site-header">
      <div className="header-inner">
        <button
          className="header-logo"
          onClick={() => navigate('/')}
          style={{ background: 'none', border: 'none', padding: 0 }}
          aria-label="סלי — דף הבית"
        >
          <SaliLogo size={30} />
          <span className="header-logo-text">
            סלי<span>.</span>
          </span>
        </button>

        {!isOnSearch && (
          <div className="header-search">
            <Search className="header-search-icon" size={16} strokeWidth={2} />
            <input
              type="search"
              className="header-search-input"
              placeholder="חפש מוצר..."
              onFocus={() => navigate('/')}
              readOnly
              style={{ cursor: 'pointer' }}
              aria-label="חיפוש מוצר"
            />
          </div>
        )}

        <div className="header-actions">
          <LocationChip />
          <button
            className="header-basket-btn"
            onClick={() => navigate('/basket')}
            aria-label={`סל קניות — ${totalItems} פריטים`}
          >
            <ShoppingBasket size={22} strokeWidth={1.8} />
            {totalItems > 0 && (
              <span className="basket-count" aria-hidden="true">
                {totalItems > 99 ? '99+' : totalItems}
              </span>
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
