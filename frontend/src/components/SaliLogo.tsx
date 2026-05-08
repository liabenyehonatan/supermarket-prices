interface SaliLogoProps {
  size?: number;
}

export function SaliLogo({ size = 32 }: SaliLogoProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path d="M10 22 L54 22 L48 54 Q47.5 58 43.5 58 L20.5 58 Q16.5 58 16 54 Z" fill="#1FA463" />
      <path
        d="M22 22 Q22 10 32 10 Q42 10 42 22"
        stroke="#1FA463"
        strokeWidth="3.5"
        strokeLinecap="round"
        fill="none"
      />
      <rect x="30.5" y="22" width="3" height="36" fill="#178551" opacity="0.3" />
      <g fill="#FFFFFF">
        <path d="M22 31 L22 50 L26 50 L26 35 L31 35 Q33 35 33 37 L33 50 L37 50 L37 36.5 Q37 31 31 31 Z" />
        <path d="M41 31 L41 43.5 Q41 46 39 46 L36 46 L36 50 L40 50 Q45 50 45 43.5 L45 31 Z" />
      </g>
    </svg>
  );
}
