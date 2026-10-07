import { useCallback, useEffect, useState } from 'react';
import { MapPin, Navigation, X, ChevronDown } from 'lucide-react';
import { fetchCities } from '../api/client';
import { FEATURED_CHAINS, matchCity } from '../lib/filters';
import { useCurrentCity } from '../lib/location';
import { ChainLogo } from './ChainLogo';
import { LocationPrompt } from './LocationPrompt';

/** City + chain filter controls (used on the basket page). */
export function StoreFilters({ city, chain, onCityChange, onChainChange }: {
  city: string;
  chain: string;
  onCityChange: (city: string) => void;
  onChainChange: (chain: string) => void;
}) {
  const [cities, setCities] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [editing, setEditing] = useState(false);
  const [chainsOpen, setChainsOpen] = useState(false);

  useEffect(() => { fetchCities().then(setCities).catch(() => {}); }, []);

  const onCity = useCallback((found: string) => {
    onCityChange(matchCity(found, cities));
    setEditing(false);
  }, [cities, onCityChange]);
  const { locate, locating, problem, dismiss } = useCurrentCity(onCity);

  const q = draft.trim();
  const suggestions = (q ? cities.filter(c => c.includes(q)) : cities).slice(0, 8);

  function pickCity(c: string) {
    onCityChange(c);
    setDraft('');
    setEditing(false);
  }

  return (
    <div className="store-filters">
      <div className="store-filters-row">
        {city && !editing ? (
          <span className="filter-chip active">
            <MapPin size={13} strokeWidth={2} />
            {city}
            <button onClick={() => onCityChange('')} aria-label="הסר סינון עיר" className="filter-chip-x">
              <X size={13} strokeWidth={2.5} />
            </button>
          </span>
        ) : (
          <div className="filter-city-input">
            <MapPin size={14} strokeWidth={2} className="filter-city-icon" />
            <input
              type="text"
              placeholder="סנן לפי עיר..."
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onFocus={() => setEditing(true)}
              onBlur={() => setTimeout(() => setEditing(false), 180)}
              onKeyDown={e => {
                if (e.key === 'Enter' && suggestions[0]) pickCity(suggestions[0]);
              }}
              aria-label="עיר לסינון"
            />
            {editing && suggestions.length > 0 && (
              <div className="filter-suggestions">
                {suggestions.map(c => (
                  <button key={c} onMouseDown={() => pickCity(c)}>
                    <MapPin size={13} strokeWidth={2} />
                    {c}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

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

      <LocationPrompt problem={problem} onRetry={locate} onClose={dismiss} />
    </div>
  );
}
