import { useState } from 'react';

export function ProductImage({
  barcode,
  name,
  imageUrl,
  size = 56,
  borderRadius = 12, // --r-md: the same tile radius everywhere
}: {
  barcode: string;
  name: string;
  /** When the API already knows the picture, load it directly: no extra round trip through our server. */
  imageUrl?: string | null;
  /** Pixels, or a CSS length such as '100%' to fill the parent (the search result cards). */
  size?: number | string;
  borderRadius?: number;
}) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const sharedStyle: React.CSSProperties = {
    width: size, height: size, flexShrink: 0, borderRadius,
  };

  return (
    <div style={{ ...sharedStyle, position: 'relative', background: '#FFFFFF', boxShadow: 'inset 0 0 0 1px var(--line)', overflow: 'hidden' }}>
      {!failed && (
        <img
          src={imageUrl || `/api/v1/products/${barcode}/image`}
          alt={name}
          loading="lazy"
          decoding="async"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          style={{
            ...sharedStyle,
            objectFit: 'contain',
            display: 'block',
            opacity: loaded ? 1 : 0, // not display:none: a lazy image that is not displayed is never fetched
            position: 'absolute', top: 0, left: 0,
          }}
        />
      )}
      {(!loaded || failed) && (
        <div style={{
          width: '100%', height: '100%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <img
            src="/icons/no-image.webp"
            alt=""
            aria-hidden
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', filter: 'brightness(1.18) contrast(1.4)' }}
          />
        </div>
      )}
    </div>
  );
}
