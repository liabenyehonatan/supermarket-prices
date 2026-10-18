import { useCallback, useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useNavigate, useLocation, NavLink } from 'react-router-dom';
import { Search, ShoppingBasket } from 'lucide-react';
import { SaliLogo } from './SaliLogo';
import { LocationChip } from './LocationChip';
import { BasketSwitcher } from './BasketSwitcher';
import { useBasket } from '../context/BasketContext';
import { HeaderSearch } from './HeaderSearch';
import { useMainSearchHidden } from '../lib/mainSearchVisibility';

export function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const { totalItems } = useBasket();

  const isOnSearch = location.pathname === '/';
  const mainSearchHidden = useMainSearchHidden();
  // On the home page the button appears once the page's own field is out of sight; elsewhere it is always there
  const showSearchButton = !isOnSearch || mainSearchHidden;
  const [searchOrigin, setSearchOrigin] = useState<DOMRect | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const closeSearch = useCallback(() => setSearchOpen(false), []);
  const headerRef = useRef<HTMLElement>(null);
  // Read when the header field loses focus: on the home page with its own field in sight, one field is enough
  const pageFieldInSight = useRef(false);
  pageFieldInSight.current = isOnSearch && !mainSearchHidden;
  const closeOnBlur = useCallback(() => pageFieldInSight.current, []);

  function openSearch(from: HTMLElement) {
    setSearchOrigin(from.getBoundingClientRect());
    // Rendered and focused within the tap itself, or a phone will not raise its keyboard
    flushSync(() => setSearchOpen(true));
    headerRef.current?.querySelector<HTMLInputElement>('.header-search-field-input')?.focus();
  }

  // Scrolled back to the page's own field: the header one is no longer needed (unless it is being typed in)
  useEffect(() => {
    if (!searchOpen || !isOnSearch || mainSearchHidden) return;
    const input = headerRef.current?.querySelector('.header-search-field-input');
    if (document.activeElement !== input) setSearchOpen(false);
  }, [searchOpen, isOnSearch, mainSearchHidden]);

  return (
    <header className="site-header" ref={headerRef}>
      <div className="header-inner">
        <button
          className="header-logo"
          onClick={() => navigate('/')}
          style={{ background: 'none', border: 'none', padding: 0 }}
          aria-label="סלי — דף הבית"
        >
          <SaliLogo size={34} />
          <span className="header-logo-text">
            סלי<span>.</span>
          </span>
        </button>

        <nav className="header-nav" aria-label="ניווט ראשי">
          <NavLink to="/" end className={({ isActive }) => `header-nav-link${isActive ? ' active' : ''}`}>בית</NavLink>
          <NavLink to="/basket" className={({ isActive }) => `header-nav-link${isActive ? ' active' : ''}`}>הסלים שלי</NavLink>
          <NavLink to="/scan" className={({ isActive }) => `header-nav-link${isActive ? ' active' : ''}`}>סריקת ברקוד</NavLink>
        </nav>

        {!isOnSearch && (
          <div className="header-search">
            <Search className="header-search-icon" size={16} strokeWidth={2} />
            <input
              type="search"
              className="header-search-input"
              placeholder="חפשו מוצר..."
              onClick={e => openSearch(e.currentTarget)}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openSearch(e.currentTarget); } }}
              readOnly
              style={{ cursor: 'pointer' }}
              aria-label="חיפוש מוצר"
            />
          </div>
        )}

        <div className="header-actions">
          {showSearchButton && (
            <button
              type="button"
              className={`header-search-toggle${isOnSearch ? '' : ' is-compact-only'}`}
              onClick={e => openSearch(e.currentTarget)}
              aria-label="חיפוש מוצר"
              aria-expanded={searchOpen}
            >
              <Search size={18} strokeWidth={2} />
            </button>
          )}
          <LocationChip />
          {location.pathname !== '/basket' && <BasketSwitcher variant="pill" />}
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
      {searchOpen && <HeaderSearch origin={searchOrigin} onClose={closeSearch} closeOnBlur={closeOnBlur} />}
    </header>
  );
}
