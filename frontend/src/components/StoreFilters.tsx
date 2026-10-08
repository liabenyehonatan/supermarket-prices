import { useCallback, useEffect, useState } from 'react';
import { Navigation, X, ChevronDown } from 'lucide-react';
import { fetchCities } from '../api/client';
import { FEATURED_CHAINS, matchCity } from '../lib/filters';
import { useCurrentCity } from '../lib/location';
import { ChainLogo } from './ChainLogo';
import { CityPicker } from './CityPicker';
import { LocationPrompt } from './LocationPrompt';

/** City + chain filter controls (used on the basket page). */
export function StoreFilters({ city, chain, onCityChange, onChainChange }: {
  city: string;
  chain: string;
  onCityChange: (city: string) => void;
  onChainChange: (chain: string) => void;
}) {
  const [cities, setCities] = useState<string[]>([]);
  const [chainsOpen, setChainsOpen] = useState(false);

  useEffect(() => { fetchCities().then(setCities).catch(() => {}); }, []);

  const onCity = useCallback((found: string) => {
    onCityChange(matchCity(found, cities));
  }, [cities, onCityChange]);
  const { locate, request, pickCity, suggestedCity, locating, problem, dismiss } = useCurrentCity(onCity);

  return (
    <div className="store-filters">
      <div className="store-filters-row">
        <CityPicker value={city} cities={cities} onChange={onCityChange} placeholder="סנן לפי עיר..." />

        <button className="filter-chip" onClick={locate} disabled={locating}>
          <Navigation size={13} strokeWidth={2} />
          {locating ? 'מאתר...' : 'לפי מיקום נוכחי'}
        </button>

        <button
          className={`filter-chip${chain ? ' active' : ''}`}
          onClick={() => setChainsOpen(v => !v)}
          aria-expanded={chainsOpen}
        >
          {chain ? <><ChainLogo name={chain} size={18} />{chain}</> : 'כל הרשתות'}
          <ChevronDown size={13} strokeWidth={2.5} style={{ opacity: 0.6 }} />
        </button>
        {chain && (
          <button className="filter-chip-x" onClick={() => onChainChange('')} aria-label="הסר סינון רשת">
            <X size={13} strokeWidth={2.5} />
          </button>
        )}
      </div>

      {chainsOpen && (
        <div className="filter-chains">
          {FEATURED_CHAINS.map(name => (
            <button
              key={name}
              className={chain === name ? 'selected' : ''}
              onClick={() => { onChainChange(chain === name ? '' : name); setChainsOpen(false); }}
              aria-pressed={chain === name}
            >
              <ChainLogo name={name} size={36} />
              <span>{name}</span>
            </button>
          ))}
        </div>
      )}

      <LocationPrompt problem={problem} onRetry={locate} onConfirm={request} onPickCity={pickCity} suggestedCity={suggestedCity} onClose={dismiss} />
    </div>
  );
}
