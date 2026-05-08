interface SparklineProps {
  prices: number[];
  width?: number;
  height?: number;
  color?: string;
}

export function PriceSparkline({ prices, width = 300, height = 64, color = '#1FA463' }: SparklineProps) {
  if (prices.length < 2) return null;

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pad = 8;
  const w = width;
  const h = height;
  const innerH = h - pad * 2;
  const innerW = w - pad * 2;
  const step = innerW / (prices.length - 1);

  const points = prices.map((p, i) => ({
    x: pad + i * step,
    y: pad + innerH - ((p - min) / range) * innerH,
  }));

  const linePath = points
    .map((pt, i) => `${i === 0 ? 'M' : 'L'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`)
    .join(' ');

  const areaPath =
    `${linePath} L${points[points.length - 1].x.toFixed(1)},${(h - pad).toFixed(1)} L${pad},${(h - pad).toFixed(1)} Z`;

  const last = points[points.length - 1];
  const isDown = prices[prices.length - 1] <= prices[0];

  return (
    <svg
      className="sparkline-svg"
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      aria-label="גרף היסטוריית מחירים"
    >
      <defs>
        <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Area fill */}
      <path d={areaPath} fill="url(#sparkGrad)" />

      {/* Line */}
      <path
        d={linePath}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Data points */}
      {points.map((pt, i) => (
        <circle
          key={i}
          cx={pt.x}
          cy={pt.y}
          r={i === points.length - 1 ? 4 : 2.5}
          fill={i === points.length - 1 ? color : '#fff'}
          stroke={color}
          strokeWidth="1.5"
        />
      ))}

      {/* Latest price label */}
      <text
        x={last.x > w * 0.7 ? last.x - 6 : last.x + 6}
        y={last.y - 8}
        textAnchor={last.x > w * 0.7 ? 'end' : 'start'}
        fill={isDown ? '#178551' : '#E0443A'}
        fontSize="11"
        fontWeight="700"
        fontFamily="'Rubik', sans-serif"
      >
        ₪{prices[prices.length - 1].toFixed(2)}
      </text>
    </svg>
  );
}

interface SparklineSectionProps {
  prices: number[];
  label?: string;
}

export function SparklineSection({ prices, label = 'היסטוריית מחירים — 30 יום אחרונים' }: SparklineSectionProps) {
  if (!prices.length) return null;
  const min = Math.min(...prices);
  const max = Math.max(...prices);

  return (
    <div className="sparkline-section">
      <div className="sparkline-header">
        <span className="sparkline-title">{label}</span>
        <span className="sparkline-range tabular">
          ₪{min.toFixed(2)} – ₪{max.toFixed(2)}
        </span>
      </div>
      <PriceSparkline prices={prices} />
      <div className="sparkline-price-labels">
        <span className="sparkline-price-label">30 יום</span>
        <span className="sparkline-price-label">היום</span>
      </div>
    </div>
  );
}
