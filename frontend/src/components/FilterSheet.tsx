import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Navigation, X, Check } from 'lucide-react';
import { ChainLogo } from './ChainLogo';
import { CityPicker } from './CityPicker';
import { FEATURED_CHAINS } from '../lib/filters';

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
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div className="sheet-backdrop" onClick={onClose}>
      <div className="location-sheet filter-sheet" role="dialog" aria-label="סינון חנויות" onClick={e => e.stopPropagation()}>
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
        <div className="filter-sheet-chains">
          {FEATURED_CHAINS.map(name => (
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
