import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { MapPin, Navigation, X, ChevronDown, Search, Check } from 'lucide-react';
import { fetchCities } from '../api/client';
import { LocationPrompt } from './LocationPrompt';
import { useCurrentCity } from '../lib/location';
import { matchCity, onCityFilterChange, readCityFilter, saveCityFilter } from '../lib/filters';

/** Header chip showing the active city filter; opens a small sheet to change it. */
export function LocationChip() {
  const [city, setCity] = useState(readCityFilter);
  const [open, setOpen] = useState(false);
  const [cities, setCities] = useState<string[]>([]);
  const [q, setQ] = useState('');
  const [dragY, setDragY] = useState(0);
  const [dragging, setDragging] = useState(false);
  const dragStart = useRef<number | null>(null);

  const visible = useMemo(() => {
    const sorted = [...cities].sort((a, b) => a.localeCompare(b, 'he'));
    const t = q.trim();
    return t ? sorted.filter(c => c.includes(t)) : sorted;
  }, [cities, q]);

  // Drag the handle down to dismiss
  const onDragStart = (e: React.PointerEvent) => {
    dragStart.current = e.clientY;
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onDragMove = (e: React.PointerEvent) => {
    if (dragStart.current === null) return;
    setDragY(Math.max(0, e.clientY - dragStart.current));
  };
  const onDragEnd = () => {
    if (dragStart.current === null) return;
    dragStart.current = null;
    setDragging(false);
    if (dragY > 90) setOpen(false);
    setDragY(0);
  };

  useEffect(() => onCityFilterChange(setCity), []);
  useEffect(() => {
    if (open && cities.length === 0) fetchCities().then(setCities).catch(() => {});
  }, [open, cities.length]);

  const pick = useCallback((next: string) => {
    setCity(next);
    saveCityFilter(next);
    setOpen(false);
    setQ('');
  }, []);

  const onLocatedCity = useCallback((found: string) => pick(matchCity(found, cities)), [cities, pick]);
  const { locate, request, pickCity, suggestedCity, locating, problem, dismiss } = useCurrentCity(onLocatedCity);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <>
      <button
        className={`location-chip${city ? ' active' : ' icon-only'}`}
        onClick={() => { setQ(''); setDragY(0); setOpen(true); }}
        aria-label={city ? `עיר: ${city}. שינוי` : 'כל הארץ. בחירת עיר'}
        title={city || 'כל הארץ'}
      >
        <MapPin size={15} strokeWidth={2} />
        {city && <span className="location-chip-label">{city}</span>}
        <ChevronDown size={14} strokeWidth={2} />
      </button>

      {/* Portal: the header's backdrop-filter would otherwise trap this fixed overlay inside the header */}
      {open && createPortal(
        <div className="sheet-backdrop" onClick={() => setOpen(false)}>
          <div
            className="location-sheet"
            role="dialog"
            aria-label="בחירת מיקום"
            style={{ transform: `translateY(${dragY}px)`, transition: dragging ? 'none' : undefined }}
            onClick={e => e.stopPropagation()}
          >
            <div
              className="sheet-grab"
              onPointerDown={onDragStart}
              onPointerMove={onDragMove}
              onPointerUp={onDragEnd}
              onPointerCancel={onDragEnd}
            >
              <span className="sheet-handle" />
            </div>
            <div className="location-sheet-head">
              <strong>איפה לחפש מחירים?</strong>
              <button className="location-sheet-close" onClick={() => setOpen(false)} aria-label="סגור">
                <X size={18} strokeWidth={2.5} />
              </button>
            </div>

            <div className="location-search">
              <Search size={16} strokeWidth={2} />
              <input
                value={q}
                onChange={e => setQ(e.target.value)}
                placeholder="חיפוש עיר"
                aria-label="חיפוש עיר"
                autoComplete="off"
              />
            </div>

            <div className="location-list" role="listbox">
              {!q && (
                <>
                  <button className="location-row location-row-gps" onClick={() => { setOpen(false); void locate(); }} disabled={locating}>
                    <Navigation size={17} strokeWidth={2} />
                    <span>{locating ? 'מאתר מיקום...' : 'המיקום הנוכחי שלי'}</span>
                  </button>
                  <button className="location-row" role="option" aria-selected={!city} onClick={() => pick('')}>
                    <span>כל הארץ</span>
                    {!city && <Check size={17} strokeWidth={2.5} />}
                  </button>
                </>
              )}
              {visible.map(c => (
                <button key={c} className="location-row" role="option" aria-selected={c === city} onClick={() => pick(c)}>
                  <span>{c}</span>
                  {c === city && <Check size={17} strokeWidth={2.5} />}
                </button>
              ))}
              {q && visible.length === 0 && <p className="location-empty">לא נמצאה עיר בשם הזה</p>}
            </div>
          </div>
        </div>,
        document.body
      )}

      <LocationPrompt problem={problem} onRetry={locate} onConfirm={request} onPickCity={pickCity} suggestedCity={suggestedCity} onClose={dismiss} />
    </>
  );
}
