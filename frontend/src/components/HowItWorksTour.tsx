import { useCallback, useEffect, useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { fetchStats } from '../api/client';
import { hasSeen, markSeen } from '../lib/firstVisit';
import { useFocusTrap } from '../lib/useFocusTrap';

const SEEN_KEY = 'sali_seen_tour';

function CompareTrendIcon() {
  // Thin line arrow trending up, drawn to match the line-art illustrations of the other steps
  return (
    <svg width="56" height="56" viewBox="0 0 48 48" fill="none" aria-hidden
      stroke="#4D6B39" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 37 L17 26 L25 32 L41 16" />
      <path d="M31 16 L41 16 L41 26" />
    </svg>
  );
}

interface Step {
  /** The first visible element of these is highlighted; none visible: the card sits in the middle. */
  targets: string[];
  art: React.ReactNode;
  title: string;
  text: (chains: number | null) => string;
}

const STEPS: Step[] = [
  {
    targets: ['.search-hero-input'],
    art: <img src="/icons/search-apple.webp" alt="" aria-hidden />,
    title: 'מחפשים מוצר',
    text: () => 'כותבים שם, מותג או ברקוד, או סורקים את הברקוד במצלמה.',
  },
  {
    targets: ['.header-basket-btn', '.basket-pill'],
    art: <img src="/icons/basket-plant.webp" alt="" aria-hidden />,
    title: 'מוסיפים לסל',
    text: () => 'כל מוצר שמוסיפים נכנס לסל הפעיל. אפשר להחזיק כמה סלים, למשל לשבת ולשבוע.',
  },
  {
    targets: ['.bottom-nav a[href="/basket"]', '.header-basket-btn'],
    art: <CompareTrendIcon />,
    title: 'משווים בין הרשתות',
    text: chains => `בסל רואים כמה עולה כל הקנייה בכל סניף, מהזול ליקר${chains && chains > 1 ? `. המחירים מ-${chains} רשתות ומתעדכנים פעמיים ביום` : ''}.`,
  },
];

function visibleTarget(selectors: string[]): HTMLElement | null {
  for (const sel of selectors) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el && el.getClientRects().length && getComputedStyle(el).display !== 'none') return el;
  }
  return null;
}

/**
 * "How it works", shown once on the first visit (remembered in localStorage): a short tour that dims the page and
 * points at the real controls, one step at a time. Skippable at any step; Escape closes it.
 */
export function HowItWorksTour() {
  const [open, setOpen] = useState(() => !hasSeen(SEEN_KEY));
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [chains, setChains] = useState<number | null>(null);
  const trapRef = useFocusTrap();

  useEffect(() => { if (open) fetchStats().then(s => setChains(s.chains)).catch(() => {}); }, [open]);

  const close = useCallback(() => { setOpen(false); markSeen(SEEN_KEY); }, []);

  // Follow the highlighted element when the page lays out, scrolls or resizes
  useLayoutEffect(() => {
    if (!open) return;
    const measure = () => setRect(visibleTarget(STEPS[step].targets)?.getBoundingClientRect() ?? null);
    measure();
    const late = window.setTimeout(measure, 350);      // the banner image and fonts can still move things
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, { passive: true });
    return () => {
      window.clearTimeout(late);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure);
    };
  }, [open, step]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
      // RTL: the right arrow goes back, the left arrow goes forward
      if (e.key === 'ArrowLeft') setStep(s => Math.min(STEPS.length - 1, s + 1));
      if (e.key === 'ArrowRight') setStep(s => Math.max(0, s - 1));
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, close]);

  if (!open) return null;
  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  const pad = 6;
  const hole = rect && {
    top: rect.top - pad, left: rect.left - pad, width: rect.width + pad * 2, height: rect.height + pad * 2,
  };
  // The card goes on the side of the highlight with more room; without a highlight it is centred
  const below = hole ? hole.top + hole.height / 2 < window.innerHeight / 2 : false;
  const cardStyle: React.CSSProperties = hole
    ? below ? { top: hole.top + hole.height + 14 } : { bottom: window.innerHeight - hole.top + 14 }
    : { top: '50%', transform: 'translateY(-50%)' };

  return createPortal(
    <div className="tour" role="presentation">
      {hole
        ? <div className="tour-hole" style={hole} aria-hidden />
        : <div className="tour-shade" aria-hidden />}
      <div className="tour-catcher" aria-hidden />   {/* blocks the page; closing is the X, "דלגו" or Escape */}
      <div
        className={`tour-card${hole ? (below ? ' is-below' : ' is-above') : ''}`}
        style={cardStyle}
        role="dialog" aria-modal="true" aria-labelledby="tour-title" aria-describedby="tour-text"
        tabIndex={-1} ref={trapRef}
      >
        <button className="tour-close" onClick={close} aria-label="סגירת ההדרכה"><X size={16} strokeWidth={2.5} /></button>
        <div className="tour-step-count">שלב {step + 1} מתוך {STEPS.length}</div>
        <div className="tour-body" key={step}>
          <div className="tour-art">{s.art}</div>
          <div>
            <h2 className="tour-title" id="tour-title">{s.title}</h2>
            <p className="tour-text" id="tour-text">{s.text(chains)}</p>
          </div>
        </div>
        <div className="tour-foot">
          <div className="tour-dots" aria-hidden>
            {STEPS.map((_, i) => <span key={i} className={i === step ? 'on' : ''} />)}
          </div>
          <div className="tour-actions">
            {step > 0
              ? <button className="btn btn-ghost btn-sm" onClick={() => setStep(step - 1)}>הקודם</button>
              : <button className="btn btn-ghost btn-sm" onClick={close}>דלגו</button>}
            <button className="btn btn-primary btn-sm" onClick={() => (last ? close() : setStep(step + 1))}>
              {last ? 'בואו נתחיל' : 'הבא'}
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
