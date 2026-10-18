import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Search, X } from 'lucide-react';

const DEBOUNCE_MS = 320;

/**
 * The search field that opens inside the header (the home page's own field is out of sight, or another page).
 * It grows out of the button that opened it, covers the header, and searches as you type: the results are the home
 * page's, scrolled so the first ones sit right under the header. "ביטול" or Escape folds it back into the button.
 */
export function HeaderSearch({ origin, onClose, closeOnBlur }: {
  /** The button it grows out of (and shrinks back into) */
  origin: DOMRect | null;
  onClose: () => void;
  /** Asked when the field loses focus: true folds it away (the page's own field is in sight again) */
  closeOnBlur: () => boolean;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const onHome = location.pathname === '/';
  const [value, setValue] = useState(() => (onHome ? params.get('q') ?? '' : ''));
  const popRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closing = useRef(false);

  // From the button's box to the whole header, and back on close
  const clipFrom = () => {
    const pop = popRef.current;
    if (!pop || !origin) return 'inset(0 round 999px)';
    const box = pop.getBoundingClientRect();
    const top = Math.max(0, origin.top - box.top), bottom = Math.max(0, box.bottom - origin.bottom);
    const left = Math.max(0, origin.left - box.left), right = Math.max(0, box.right - origin.right);
    return `inset(${top}px ${right}px ${bottom}px ${left}px round 999px)`;
  };
  const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

  useLayoutEffect(() => {
    inputRef.current?.focus();
    const pop = popRef.current;
    if (!pop || reduced() || typeof pop.animate !== 'function') return;
    pop.animate([{ clipPath: clipFrom() }, { clipPath: 'inset(0 round 0px)' }], { duration: 300, easing: 'cubic-bezier(0.2, 0, 0, 1)' });
  }, []);

  function close() {
    if (closing.current) return;
    closing.current = true;
    if (timer.current) clearTimeout(timer.current);
    const pop = popRef.current;
    if (!pop || reduced() || typeof pop.animate !== 'function') { onClose(); return; }
    const anim = pop.animate([{ clipPath: 'inset(0 round 0px)' }, { clipPath: clipFrom() }],
      { duration: 220, easing: 'cubic-bezier(0.4, 0, 1, 1)', fill: 'forwards' });
    // Closed when the fold ends, or shortly after in any case (a background tab may never finish an animation)
    let done = false;
    const finish = () => { if (!done) { done = true; onClose(); } };
    anim.onfinish = finish;
    window.setTimeout(finish, 400);
  }

  // Leaving the page (a result was opened) closes it at once
  const path = useRef(location.pathname);
  useEffect(() => {
    if (location.pathname !== path.current && location.pathname !== '/') onClose();
    path.current = location.pathname;
  }, [location.pathname, onClose]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); if (timer.current) clearTimeout(timer.current); };
  }, []);

  function search(q: string) {
    const trimmed = q.trim();
    // The first search from another page opens the results (back returns to that page); after that it only refines
    navigate(trimmed ? `/?q=${encodeURIComponent(trimmed)}` : '/', { replace: location.pathname === '/' });
    // New results start at the top: scroll so the home field stays just out of sight and the first cards sit under the header
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const panel = document.querySelector('.search-panel-box');
      const headerH = document.querySelector<HTMLElement>('.site-header')?.offsetHeight ?? 64;
      if (!panel) return;
      const top = panel.getBoundingClientRect().bottom + window.scrollY - headerH + 1;
      if (window.scrollY > top) window.scrollTo({ top, behavior: 'instant' as ScrollBehavior });
    }));
  }

  function onInput(v: string) {
    setValue(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => search(v), DEBOUNCE_MS);
  }

  return (
    <div className="header-search-pop" ref={popRef} role="search">
      <div className="header-search-field">
        <Search size={18} strokeWidth={2} className="header-search-field-icon" aria-hidden />
        <input
          ref={inputRef}
          type="search"
          enterKeyHint="search"
          className="header-search-field-input"
          placeholder="חפשו מוצר, מותג או ברקוד"
          value={value}
          onChange={e => onInput(e.target.value)}
          onBlur={() => { if (closeOnBlur()) close(); }}
          onKeyDown={e => {
            if (e.key !== 'Enter') return;
            if (timer.current) clearTimeout(timer.current);
            search(value);
            e.currentTarget.blur();   // closes the phone keyboard; the field stays open
          }}
          aria-label="חיפוש מוצר"
        />
        {value && (
          <button type="button" className="header-search-field-clear" onMouseDown={e => e.preventDefault()} onClick={() => { onInput(''); inputRef.current?.focus(); }} aria-label="ניקוי החיפוש">
            <X size={13} strokeWidth={2.5} />
          </button>
        )}
      </div>
      <button type="button" className="header-search-cancel" onClick={close}>ביטול</button>
    </div>
  );
}
