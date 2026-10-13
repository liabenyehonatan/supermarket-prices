import { useEffect, useState } from 'react';
import { useFocusTrap } from '../lib/useFocusTrap';
import { createPortal } from 'react-dom';
import { Navigation, X, Check, Search } from 'lucide-react';
import { ChainLogo } from './ChainLogo';
import { CityPicker } from './CityPicker';
import { useChainNames } from '../lib/filters';

/** Bottom sheet for the product page: city, chain and "use my location" in one place. */
export function FilterSheet({ city, cities, chain, locating, onCity, onChain, onLocate, onClose }: {
  city: string;
  cities: string[];
  chain: string;
  locating: boolean;
  onCity: (city: string) => void;
  onChain: (chain: string) => void;
  onLocate: () => void;
  onClose: () => void;
}) {
  const trapRef = useFocusTrap();
  const [chainQuery, setChainQuery] = useState('');
  const chainNames = useChainNames();
  const visibleChains = chainNames.filter(name => name.includes(chainQuery.trim()));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="location-sheet filter-sheet" role="dialog" aria-modal="true" tabIndex={-1} ref={trapRef} aria-label="סינון חנויות" onClick={e => e.stopPropagation()}>
        <div className="sheet-grab"><div className="sheet-handle" /></div>
        <div className="location-sheet-head">
          <strong>סינון חנויות</strong>
          <button className="location-sheet-close" onClick={onClose} aria-label="סגירה"><X size={20} /></button>
        </div>

        <div className="filter-sheet-label">עיר</div>
        <div className="filter-sheet-city">
          <CityPicker value={city} cities={cities} onChange={onCity} placeholder="חפשי עיר..." />
          <button className="filter-sheet-locate" onClick={onLocate} disabled={locating}>
            <Navigation size={15} strokeWidth={2} />
            {locating ? 'מאתר...' : 'המיקום שלי'}
          </button>
        </div>

        <div className="filter-sheet-label">רשת</div>
        <label className="chain-search">
          <Search size={15} strokeWidth={2} aria-hidden />
          <input
            type="search"
            value={chainQuery}
            onChange={e => setChainQuery(e.target.value)}
            placeholder="חפשי רשת..."
            aria-label="חיפוש רשת"
          />
        </label>
        <div className="filter-sheet-chains">
          {visibleChains.length === 0 && <div className="chain-search-empty">לא נמצאה רשת בשם הזה</div>}
          {visibleChains.map(name => (
            <button
              key={name}
              className={`filter-chain${chain === name ? ' selected' : ''}`}
              onClick={() => onChain(chain === name ? '' : name)}
              aria-pressed={chain === name}
            >
              <ChainLogo name={name} size={36} />
              <span>{name}</span>
              {chain === name && <Check size={12} strokeWidth={3} className="filter-chain-check" />}
            </button>
          ))}
        </div>

        <button className="btn btn-primary btn-full filter-sheet-done" onClick={onClose}>הצג תוצאות</button>
      </div>
    </div>,
    document.body,
  );
}
