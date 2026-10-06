/* Full-width basket photo banner for the search home screen. */
export function HeroBanner({ title }: { title: string }) {
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
      </div>
    </div>
  );
}
