import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';

interface Slide {
  id: string;
  title: string;
  sub: string;
  cta: string;
  /** a route to open, or 'search' to move to the search field */
  to: string;
  tone: 'forest' | 'ocean' | 'amber';
}

const SLIDES: Slide[] = [
  { id: 'compare', title: 'השוואת מחירי סופרמרקט', sub: 'כל הרשתות, במקום אחד', cta: 'חיפוש מוצר', to: 'search', tone: 'forest' },
  { id: 'scan', title: 'סורקים ברקוד', sub: 'ורואים מיד איפה הכי זול', cta: 'לסריקה', to: '/scan', tone: 'ocean' },
  { id: 'deals', title: 'מבצעים שבאמת זולים', sub: 'רק כאלה שזולים מהמחיר שמצאנו', cta: 'למבצעים', to: '/promotions', tone: 'amber' },
];

/** The picture side of each slide: the basket photo on a plate with produce around it, or a few large pictures. */
function Art({ id }: { id: string }) {
  if (id === 'compare') {
    return (
      <div className="promo-art" aria-hidden>
        <img className="promo-plate" src="/hero-basket.webp" alt="" width={400} height={260} loading="eager" />
        <span className="promo-bit b1">🥕</span>
        <span className="promo-bit b2">🍅</span>
        <span className="promo-bit b3">🥬</span>
        <span className="promo-bit b4">🍋</span>
      </div>
    );
  }
  return (
    <div className="promo-art promo-art-emoji" aria-hidden>
      <span className="promo-big e1">{id === 'scan' ? '📱' : '🏷️'}</span>
      <span className="promo-big e2">{id === 'scan' ? '🥫' : '🛒'}</span>
      <span className="promo-bit b1">{id === 'scan' ? '🍎' : '🥦'}</span>
      <span className="promo-bit b3">{id === 'scan' ? '🥛' : '🍊'}</span>
    </div>
  );
}

/** The home banner: a big colourful picture, a line of text and a white button; swipe for the next one, dots show where you are. */
export function PromoBanner({ onSearch }: { onSearch: () => void }) {
  const navigate = useNavigate();
  const trackRef = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  const onScroll = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    const w = el.clientWidth;
    if (w > 0) setIndex(Math.min(SLIDES.length - 1, Math.round(Math.abs(el.scrollLeft) / w)));
  }, []);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, [onScroll]);

  function go(i: number) {
    const el = trackRef.current;
    if (!el) return;
    const isRtl = getComputedStyle(el).direction === 'rtl';
    el.scrollTo({ left: (isRtl ? -1 : 1) * i * el.clientWidth, behavior: 'smooth' });
  }

  return (
    <section className="promo" aria-roledescription="carousel" aria-label="הצעות">
      <div className="promo-track" ref={trackRef}>
        {SLIDES.map((s, i) => (
          <div key={s.id} className={`promo-slide tone-${s.tone}`} aria-hidden={i !== index || undefined}>
            <Art id={s.id} />
            <div className="promo-text">
              <h2 className="promo-title">{s.title}</h2>
              <p className="promo-sub">{s.sub}</p>
              <button
                type="button"
                className="promo-cta"
                tabIndex={i === index ? 0 : -1}
                onClick={() => (s.to === 'search' ? onSearch() : navigate(s.to))}
              >
                {s.cta}
                <ChevronLeft size={14} strokeWidth={2.5} aria-hidden />
              </button>
            </div>
          </div>
        ))}
      </div>
      <div className="promo-dots" role="tablist" aria-label="בחירת הצעה">
        {SLIDES.map((s, i) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={i === index}
            aria-label={`הצעה ${i + 1} מתוך ${SLIDES.length}`}
            className={`promo-dot${i === index ? ' on' : ''}`}
            onClick={() => go(i)}
          />
        ))}
      </div>
    </section>
  );
}
