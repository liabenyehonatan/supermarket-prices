import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { ChainLogo } from './ChainLogo';

/** Horizontal chain picker: a row of round logos, with arrows that appear while there is more to see. */
export function ChainCarousel({ chains: allChains, selected, onSelect, style, counts }: {
  chains: string[];
  counts?: Record<string, number>;     // an optional number under each logo (e.g. how many deals the chain has)
  selected: string;
  onSelect: (name: string) => void;
  style?: CSSProperties;
}) {
  const [query, setQuery] = useState('');
  const chains = query.trim() ? allChains.filter(name => name.includes(query.trim())) : allChains;
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
  }, [update, query, allChains.length]);   // measure again when the list arrives (the deals page loads it late)

  // dir 1 = forward (toward the end of the list)
  function step(dir: 1 | -1) {
    const track = trackRef.current;
    if (!track) return;
    const isRtl = getComputedStyle(track).direction === 'rtl';
    const amount = track.clientWidth * 0.6 * dir;
    track.scrollBy({ left: isRtl ? -amount : amount, behavior: 'smooth' });
  }

  return (
    <>
    {allChains.length > 8 && (
      <label className="chain-search" style={style}>
        <Search size={15} strokeWidth={2} aria-hidden />
        <input
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="חפשי רשת..."
          aria-label="חיפוש רשת"
        />
      </label>
    )}
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
            aria-label={counts?.[name] != null ? `סנן לפי ${name}, ${counts[name] === 1 ? 'מבצע אחד' : `${counts[name]} מבצעים`}` : `סנן לפי ${name}`}
            aria-pressed={selected === name}
          >
            <ChainLogo name={name} size={50} showLabel />
            {counts?.[name] != null && <span className="chain-carousel-count tabular">{counts[name]}</span>}
          </button>
        ))}
      </div>
      {canFwd && (
        <button className="chain-carousel-arrow end" onClick={() => step(1)} aria-label="רשתות נוספות">
          <ChevronLeft size={18} strokeWidth={2.5} />
        </button>
      )}
      {chains.length === 0 && <div className="chain-search-empty">לא נמצאה רשת בשם הזה</div>}
    </div>
    </>
  );
}
