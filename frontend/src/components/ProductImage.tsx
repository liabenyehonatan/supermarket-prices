import { useState } from 'react';

export function ProductImage({
  barcode,
  name,
  size = 56,
  borderRadius = 12, // --r-md: the same tile radius everywhere
}: {
  barcode: string;
  name: string;
  size?: number;
  borderRadius?: number;
}) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const sharedStyle: React.CSSProperties = {
    width: size, height: size, flexShrink: 0, borderRadius,
  };

  return (
    <div style={{ ...sharedStyle, position: 'relative', background: '#DDEBD6', overflow: 'hidden' }}>
      {!failed && (
        <img
          src={`/api/v1/products/${barcode}/image`}
          alt={name}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
          style={{
            ...sharedStyle,
            objectFit: 'contain',
            display: loaded ? 'block' : 'none',
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
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        </div>
      )}
    </div>
  );
}
