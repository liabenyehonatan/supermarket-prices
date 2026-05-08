interface ChainBadgeProps {
  name: string;
  width?: number;
  height?: number;
  fontSize?: number;
}

const CHAIN_COLORS: Record<string, { bg: string; fg: string }> = {
  'שופרסל':   { bg: '#E22E2E', fg: '#FFFFFF' },
  'רמי לוי':  { bg: '#FFD400', fg: '#1A1A1A' },
  'ויקטורי':  { bg: '#0A4FA0', fg: '#FFFFFF' },
  'מגה':      { bg: '#0E8A3E', fg: '#FFFFFF' },
  'יוחננוף':  { bg: '#7A1F1F', fg: '#FFFFFF' },
  'טיב טעם':  { bg: '#222222', fg: '#FFFFFF' },
  'אושר עד':  { bg: '#1B6F2A', fg: '#FFFFFF' },
  'חצי חינם': { bg: '#D4000A', fg: '#FFFFFF' },
  'כוחנית':   { bg: '#004B87', fg: '#FFFFFF' },
};

function colorForChain(name: string): { bg: string; fg: string } {
  // Direct match
  if (CHAIN_COLORS[name]) return CHAIN_COLORS[name];
  // Partial match
  for (const key of Object.keys(CHAIN_COLORS)) {
    if (name.includes(key) || key.includes(name)) return CHAIN_COLORS[key];
  }
  // Deterministic fallback from name hash
  const palettes = [
    { bg: '#5C6573', fg: '#FFFFFF' },
    { bg: '#2A6FDB', fg: '#FFFFFF' },
    { bg: '#178551', fg: '#FFFFFF' },
    { bg: '#B85008', fg: '#FFFFFF' },
    { bg: '#7A1F1F', fg: '#FFFFFF' },
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash += name.charCodeAt(i);
  return palettes[hash % palettes.length];
}

export function ChainBadge({ name, width = 56, height = 36, fontSize }: ChainBadgeProps) {
  const { bg, fg } = colorForChain(name);
  const fs = fontSize ?? Math.max(10, height * 0.34);
  return (
    <div
      className="chain-badge"
      style={{
        width,
        height,
        background: bg,
        color: fg,
        fontSize: fs,
      }}
    >
      {name}
    </div>
  );
}
