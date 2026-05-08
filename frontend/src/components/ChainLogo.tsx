import { useState } from 'react';

/* Map chain names → public logo paths */
const LOGO_MAP: Record<string, string> = {
  'שופרסל':   '/logos/shufersal.png',
  'רמי לוי':  '/logos/rami-levy.png',
  'ויקטורי':  '/logos/victory.png',
  'מגה':      '/logos/mega.png',
  'יוחננוף':  '/logos/yohananof.png',
  'טיב טעם':  '/logos/tiv-taam.png',
  'קרפור':    '/logos/carrefour.png',
  'אושר עד':  '/logos/osher-ad.png',
  'חצי חינם': '/logos/hatzi-hinam.png',
  'סופריודה': '/logos/super-yuda.png',
  'יוניברס':  '/logos/universe.png',
};

/* Logos that have their own solid background — fill edge-to-edge, no padding */
const LOGO_FILLS_CONTAINER = new Set(['טיב טעם']);

/* Fallback colored initials for chains without images */
const FALLBACK_COLORS: Record<string, { bg: string; fg: string; abbr: string }> = {
  'ויקטורי':  { bg: '#003DA5', fg: '#fff', abbr: 'V' },
  'AM:PM':    { bg: '#2C2C2C', fg: '#fff', abbr: 'AM' },
  'כוחנית':   { bg: '#0057A8', fg: '#fff', abbr: 'K' },
  'ברנע':     { bg: '#E8510C', fg: '#fff', abbr: 'B' },
  'שוק העיר': { bg: '#4A4A4A', fg: '#fff', abbr: 'SH' },
};

function resolveLogoPath(name: string): string | null {
  if (LOGO_MAP[name]) return LOGO_MAP[name];
  for (const [key, path] of Object.entries(LOGO_MAP)) {
    if (name.includes(key) || key.includes(name)) return path;
  }
  return null;
}

function resolveFallback(name: string): { bg: string; fg: string; abbr: string } {
  if (FALLBACK_COLORS[name]) return FALLBACK_COLORS[name];
  for (const [key, val] of Object.entries(FALLBACK_COLORS)) {
    if (name.includes(key) || key.includes(name)) return val;
  }
  // Deterministic color from name hash
  const pools = ['#5C6573','#2A6FDB','#178551','#B85008','#6B0F1A'];
  let h = 0;
  for (let i = 0; i < name.length; i++) h += name.charCodeAt(i);
  return { bg: pools[h % pools.length], fg: '#fff', abbr: name.slice(0, 2) };
}

interface ChainLogoProps {
  name: string;
  size?: number;
  showLabel?: boolean;
}

export function ChainLogo({ name, size = 44, showLabel = false }: ChainLogoProps) {
  const [imgError, setImgError] = useState(false);
  const logoPath = resolveLogoPath(name);
  const showImg = logoPath && !imgError;

  const containerStyle: React.CSSProperties = {
    width: size,
    height: size,
    borderRadius: Math.round(size * 0.22),
    flexShrink: 0,
    overflow: 'hidden',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  };

  let inner: React.ReactNode;

  if (showImg) {
    const fillsContainer = LOGO_FILLS_CONTAINER.has(name);
    inner = (
      <div style={{
        ...containerStyle,
        background: fillsContainer ? 'transparent' : '#fff',
        border: fillsContainer ? 'none' : '1px solid rgba(0,0,0,0.07)',
        padding: fillsContainer ? 0 : Math.round(size * 0.1),
        boxSizing: 'border-box',
        overflow: 'hidden',
      }}>
        <img
          src={logoPath}
          alt={name}
          onError={() => setImgError(true)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: fillsContainer ? 'cover' : 'contain',
            display: 'block',
          }}
        />
      </div>
    );
  } else {
    const fb = resolveFallback(name);
    inner = (
      <div style={{
        ...containerStyle,
        background: fb.bg,
        color: fb.fg,
        fontFamily: 'var(--font-sans)',
        fontWeight: 800,
        fontSize: Math.round(size * 0.35),
        letterSpacing: '-0.02em',
      }}>
        {fb.abbr}
      </div>
    );
  }

  if (showLabel) {
    return (
      <div className="chain-logo-wrap">
        <div className="chain-logo-mark" style={{ width: size, height: size }}>
          {inner}
        </div>
        <span className="chain-logo-name">{name}</span>
      </div>
    );
  }

  return <div className="chain-logo-mark" style={{ width: size, height: size }}>{inner}</div>;
}
