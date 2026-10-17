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
  /** a photo in public/banner */
  img: string;
}

const SLIDES: Slide[] = [
  { id: 'compare', title: 'השוואת מחירי סופרמרקטים', sub: 'כל ההשוואות במקום אחד', cta: 'השווה עכשיו', to: 'search', img: '/banner/basket.jpg' },
  { id: 'scan', title: 'סורקים ברקוד', sub: 'ורואים מיד איפה הכי זול', cta: 'לסריקה', to: '/scan', img: '/banner/scan.jpg' },
  { id: 'deals', title: 'מבצעים שבאמת זולים', sub: 'זולים מהמחיר שמצאנו', cta: 'למבצעים', to: '/promotions', img: '/banner/veggies-wood.jpg' },
];

/** The home banner: a bright photo on one side that melts into a deep green panel with white text and a white button; swipe for the next one, dots show where you are. */
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
          <div key={s.id} className="promo-slide" aria-hidden={i !== index || undefined}>
            <img className="promo-photo" src={s.img} alt="" width={970} height={381} loading="eager" decoding="async" />
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
