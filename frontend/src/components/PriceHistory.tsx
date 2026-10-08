import type { PriceHistoryPoint } from '../types';

const W = 320;
const H = 72;
const PAD_X = 4;
const PAD_Y = 10;

const fmt = (n: number) => `₪${n.toFixed(2)}`;
const shortDate = (iso: string) => new Date(iso).toLocaleDateString('he-IL', { day: 'numeric', month: 'short' });

/**
 * "Is today a good price?" — a one-line verdict plus a time-proportional step chart of
 * the cheapest price across all stores. Renders nothing without real history.
 */
export function PriceHistory({ points, days }: { points: PriceHistoryPoint[]; days: number }) {
  if (points.length < 2) return null;

  const data = points.map(p => ({ t: new Date(p.date).getTime(), price: Number(p.price) }));
  const prices = data.map(d => d.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const now = data[data.length - 1].price;
  const windowStart = Date.now() - days * 86_400_000;
  // Only claim "stable" when the series really spans the whole window
  const coversWindow = data[0].t <= windowStart + 2 * 86_400_000;

  if (min === max) {
    if (!coversWindow) return null;
    return <div className="price-history-note">המחיר יציב ב־{days} הימים האחרונים</div>;
  }

  let verdict: string;
  let tone: 'good' | 'bad' | 'mid';
  if (now === min) { verdict = `המחיר הנמוך ביותר ב־${days} הימים האחרונים`; tone = 'good'; }
  else if (now === max) { verdict = `המחיר הגבוה ביותר ב־${days} הימים האחרונים`; tone = 'bad'; }
  else { verdict = `${fmt(now - min)} מעל המחיר הנמוך ב־${days} הימים האחרונים`; tone = 'mid'; }

  const t0 = data[0].t;
  const span = data[data.length - 1].t - t0 || 1;
  const x = (t: number) => PAD_X + ((t - t0) / span) * (W - PAD_X * 2);
  const y = (v: number) => PAD_Y + (1 - (v - min) / (max - min)) * (H - PAD_Y * 2);

  // Step line: a price holds until the next change
  const path = data
    .map((d, i) => (i === 0 ? `M${x(d.t)},${y(d.price)}` : `H${x(d.t)}V${y(d.price)}`))
    .join(' ');
  const last = data[data.length - 1];

  return (
    <div className="price-history">
      <div className={`price-history-verdict ${tone}`}>{verdict}</div>
      <svg viewBox={`0 0 ${W} ${H}`} className="price-history-svg" role="img" aria-label="גרף היסטוריית המחיר הזול ביותר">
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(last.t)} cy={y(last.price)} r="4" fill="currentColor" />
      </svg>
      <div className="price-history-axis" dir="ltr">
        <span><bdi>{shortDate(points[0].date)}</bdi> · <bdi>{fmt(Number(points[0].price))}</bdi></span>
        <span><bdi>היום</bdi> · <bdi>{fmt(now)}</bdi></span>
      </div>
    </div>
  );
}
