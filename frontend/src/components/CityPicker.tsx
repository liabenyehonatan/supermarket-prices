import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { MapPin, X, ChevronDown, Check } from 'lucide-react';

/**
 * City selector: a text field that also opens a scrollable, alphabetical list
 * of every city — type to narrow it down, or just scroll and tap.
 * `onChange` fires only when a city is picked or cleared, never per keystroke.
 */
export function CityPicker({ value, cities, onChange, placeholder = 'בחרי או הקלידי עיר...', autoFocus, className = '' }: {
  value: string;
  cities: string[];
  onChange: (city: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  className?: string;
}) {
  const [draft, setDraft] = useState(value);
  const [open, setOpen] = useState(false);
  const [maxHeight, setMaxHeight] = useState(280);
  const [upward, setUpward] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setDraft(value); }, [value]);

  const sorted = useMemo(() => [...cities].sort((a, b) => a.localeCompare(b, 'he')), [cities]);
  const q = draft.trim();
  // While the field still shows the chosen city, list everything so the user can browse
  const options = q && q !== value ? sorted.filter(c => c.includes(q)) : sorted;

  // Close on any tap outside the picker
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) close();
    };
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  });

  // Keep the list between the field and the bottom nav bar (or the on-screen keyboard),
  // flipping it above the field when there isn't enough room below.
  useLayoutEffect(() => {
    if (!open) return;
    const fit = () => {
      const wrap = wrapRef.current;
      if (!wrap) return;
      const rect = wrap.getBoundingClientRect();
      const nav = document.querySelector('.bottom-nav');
      const navTop = nav && getComputedStyle(nav).display !== 'none'
        ? nav.getBoundingClientRect().top
        : window.innerHeight;
      const vv = window.visualViewport;
      const bottom = Math.min(navTop, vv ? vv.offsetTop + vv.height : window.innerHeight);
      const below = bottom - rect.bottom - 12;
      const above = rect.top - 72; // leave room for the sticky header
      const flip = below < 180 && above > below;
      setUpward(flip);
      setMaxHeight(Math.max(140, Math.min(320, flip ? above : below)));
    };
    fit();
    window.addEventListener('resize', fit);
    window.addEventListener('scroll', fit, { passive: true });
    window.visualViewport?.addEventListener('resize', fit);
    return () => {
      window.removeEventListener('resize', fit);
      window.removeEventListener('scroll', fit);
      window.visualViewport?.removeEventListener('resize', fit);
    };
  }, [open]);

  // Bring the selected city into view when the list opens
  useEffect(() => {
    if (!open || !value) return;
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'center' });
  }, [open, value]);

  function close() {
    setOpen(false);
    setDraft(value);
  }

  function pick(city: string) {
    onChange(city);
    setDraft(city);
    setOpen(false);
    inputRef.current?.blur();
  }

  return (
    <div ref={wrapRef} className={`city-picker ${className}`}>
      <MapPin size={14} strokeWidth={2} className="city-picker-icon" />
      <input
        ref={inputRef}
        type="text"
        value={draft}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onChange={e => { setDraft(e.target.value); setOpen(true); }}
        onFocus={e => { setOpen(true); e.target.select(); }}
        onKeyDown={e => {
          if (e.key === 'Enter' && options[0]) pick(options[0]);
          if (e.key === 'Escape') { close(); inputRef.current?.blur(); }
        }}
        role="combobox"
        aria-expanded={open}
        aria-label="עיר לסינון"
      />
      {value ? (
        <button className="city-picker-btn" onClick={() => pick('')} aria-label="נקה עיר">
          <X size={13} strokeWidth={2.5} />
        </button>
      ) : (
        <button
          className="city-picker-btn"
          onClick={() => (open ? close() : setOpen(true))}
          aria-label="הצג את כל הערים"
        >
          <ChevronDown size={15} strokeWidth={2.5} />
        </button>
      )}

      {open && (
        <div
          ref={listRef}
          className={`city-picker-list${upward ? ' upward' : ''}`}
          style={{ maxHeight }}
          role="listbox"
          // Keep focus in the field while scrolling/dragging the list
          onMouseDown={e => e.preventDefault()}
        >
          {options.length === 0 ? (
            <div className="city-picker-empty">לא נמצאה עיר בשם הזה</div>
          ) : options.map(c => (
            <button
              key={c}
              role="option"
              aria-selected={c === value}
              className={c === value ? 'selected' : ''}
              onClick={() => pick(c)}
            >
              <MapPin size={13} strokeWidth={2} />
              <span>{c}</span>
              {c === value && <Check size={14} strokeWidth={2.5} className="city-picker-check" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
