/* Full-width basket photo banner for the search home screen. */
export function HeroBanner({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="hero-banner">
      <img
        className="hero-banner-art"
        src="/hero-basket.webp"
        alt=""
        aria-hidden
        width={1024}
        height={665}
      />
      <div className="hero-banner-title">
        <h1 className="hero-title">{title}</h1>
        {subtitle && <p className="hero-sub">{subtitle}</p>}
      </div>
    </div>
  );
}
