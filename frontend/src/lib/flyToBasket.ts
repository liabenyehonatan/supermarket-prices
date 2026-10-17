// "Add to basket" feedback: a copy of the product picture is thrown in an arc into the basket, which then bounces.
// Purely decorative: the item is already in the basket when this starts.

/** The basket the picture flies into: the basket icon of the bottom bar (phones), else the header basket button (desktop). */
function basketTarget(): HTMLElement | null {
  for (const sel of ['.bottom-nav-basket-icon', '.header-basket-btn', '.basket-pill']) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el && el.getClientRects().length && getComputedStyle(el).display !== 'none') return el;
  }
  return null;
}

function bump(el: HTMLElement) {
  el.classList.remove('basket-bump');
  void el.offsetWidth;                      // restart the animation when items are added in a row
  el.classList.add('basket-bump');
  window.setTimeout(() => el.classList.remove('basket-bump'), 600);
}

/** `source` is the product picture (or any element around it) the throw starts from. */
export function flyToBasket(source: Element | null | undefined) {
  const target = basketTarget();
  if (!target) return;
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  const img = source?.querySelector?.('img:not([aria-hidden])') as HTMLImageElement | null
    ?? (source instanceof HTMLImageElement ? source : null);
  if (reduced || !source || typeof document.body.animate !== 'function') { bump(target); return; }

  const from = source.getBoundingClientRect();
  const to = target.getBoundingClientRect();
  if (!from.width || !to.width) { bump(target); return; }

  const size = Math.min(72, Math.max(40, from.width));
  const ghost = document.createElement('div');
  ghost.className = 'fly-ghost';
  ghost.style.width = ghost.style.height = `${size}px`;
  if (img && img.complete && img.naturalWidth && getComputedStyle(img).opacity !== '0') {
    const pic = img.cloneNode() as HTMLImageElement;
    pic.removeAttribute('loading');
    pic.removeAttribute('style');
    pic.alt = '';
    ghost.appendChild(pic);
  } else {
    ghost.classList.add('fly-ghost-dot');   // no picture loaded: a green dot is thrown instead
  }
  document.body.appendChild(ghost);

  const x0 = from.left + from.width / 2 - size / 2;
  const y0 = from.top + from.height / 2 - size / 2;
  const x1 = to.left + to.width / 2 - size / 2;
  const y1 = to.top + to.height / 2 - size / 2;
  // Quadratic curve whose control point sits above both ends: up and over, then down into the basket
  const cx = (x0 + x1) / 2;
  const cy = Math.min(y0, y1) - Math.max(80, Math.abs(y1 - y0) * 0.35);
  const steps = 18;
  const frames: Keyframe[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1;
    const y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1;
    const scale = 1 - 0.75 * t;
    frames.push({
      transform: `translate(${x}px, ${y}px) scale(${scale}) rotate(${-25 * t}deg)`,
      opacity: t > 0.85 ? 1 - (t - 0.85) / 0.15 * 0.7 : 1,
      offset: t,
    });
  }
  const anim = ghost.animate(frames, { duration: 700, easing: 'cubic-bezier(0.45, 0, 0.55, 1)', fill: 'forwards' });
  const done = () => { ghost.remove(); bump(target); };
  anim.onfinish = done;
  anim.oncancel = () => ghost.remove();
}
