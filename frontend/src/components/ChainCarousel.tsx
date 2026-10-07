import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { ChainLogo } from './ChainLogo';

/**
 * Horizontal chain picker shown as a 3D carousel: items tilt and shrink as they
 * move away from the center, with arrows that appear while there is more to see.
 */
export function ChainCarousel({ chains, selected, onSelect, style }: {
  chains: string[];
  selected: string;
  onSelect: (name: string) => void;
  style?: CSSProperties;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [canBack, setCanBack] = useState(false);   // toward the start (right in RTL)
  const [canFwd, setCanFwd]   = useState(false);   // toward the end (left in RTL)

  const update = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    // In RTL scrollLeft runs from 0 down to negative values
    const pos = Math.abs(track.scrollLeft);
    const max = track.scrollWidth - track.clientWidth;
    setCanBack(pos > 2);
    setCanFwd(pos < max - 2);

    const items = Array.from(track.children) as HTMLElement[];
    if (max <= 2) {
      // Everything fits — show a flat row
      for (const el of items) { el.style.transform = ''; el.style.opacity = ''; }
      return;
    }

    const box = track.getBoundingClientRect();
    const center = box.left + box.width / 2;
    for (const el of items) {
      const r = el.getBoundingClientRect();
      // -1 … 1: how far the item sits from the center, relative to half the width
      const d = Math.max(-1, Math.min(1, (r.left + r.width / 2 - center) / (box.width / 2)));
      const a = Math.abs(d);
      el.style.transform = `perspective(600px) rotateY(${d * -28}deg) scale(${1 - a * 0.18})`;
      el.style.opacity = String(1 - a * 0.35);
    }
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    update();
    let frame = 0;
    const onScroll = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(update); };
    track.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(frame);
      track.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, [update]);

  // dir 1 = forward (toward the end of the list)
  function step(dir: 1 | -1) {
    const track = trackRef.current;
    if (!track) return;
    const isRtl = getComputedStyle(track).direction === 'rtl';
    const amount = track.clientWidth * 0.6 * dir;
    track.scrollBy({ left: isRtl ? -amount : amount, behavior: 'smooth' });
  }

  return (
    <div className="chain-carousel" style={style}>
      {canBack && (
        <button className="chain-carousel-arrow start" onClick={() => step(-1)} aria-label="רשתות קודמות">
          <ChevronRight size={18} strokeWidth={2.5} />
        </button>
      )}
      <div className="chain-carousel-track" ref={trackRef}>
        {chains.map(name => (
          <button
            key={name}
            onClick={() => onSelect(name)}
            className={`chain-carousel-item${selected === name ? ' selected' : ''}${selected && selected !== name ? ' dimmed' : ''}`}
            aria-label={`סנן לפי ${name}`}
            aria-pressed={selected === name}
          >
            <ChainLogo name={name} size={52} showLabel />
          </button>
        ))}
      </div>
      {canFwd && (
        <button className="chain-carousel-arrow end" onClick={() => step(1)} aria-label="רשתות נוספות">
          <ChevronLeft size={18} strokeWidth={2.5} />
        </button>
      )}
    </div>
  );
}
