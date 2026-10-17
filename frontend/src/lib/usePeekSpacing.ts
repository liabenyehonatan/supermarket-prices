import { useLayoutEffect, type RefObject } from 'react';

const MAX_SHIFT = 8;          // px added to (or taken from) each side of every pill, at most
const MIN_SHOWN_PX = 64;      // the cut pill shows its icon and the start of its word, not the icon alone...
const MIN_SHOWN = 0.5;        // ...and at least half of itself...
const MAX_SHOWN = 0.75;       // ...but never so much that it looks whole
const TOLERANCE = 6;          // px; close enough, leave the padding alone

/**
 * A row of pills that scrolls sideways only looks scrollable when the pill at the edge is visibly cut. When the edge
 * falls just after a pill's icon, or just before its end, the row looks finished. This widens or narrows every pill's
 * side padding a little (a CSS variable, `--peek-shift`) so the edge cuts the first hidden pill well into its word.
 * Works in either direction (RTL here).
 */
export function usePeekSpacing(rowRef: RefObject<HTMLElement>, active: boolean) {
  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row || !active) return;

    const fit = () => {
      row.style.setProperty('--peek-shift', '0px');
      const rtl = getComputedStyle(row).direction === 'rtl';
      const box = row.getBoundingClientRect();
      const pills = Array.from(row.children) as HTMLElement[];
      // Measured with the row scrolled to its start, the way it first appears
      if (Math.abs(row.scrollLeft) > 1) return;
      const k = pills.findIndex(p => {
        const r = p.getBoundingClientRect();
        return rtl ? r.left < box.left - 0.5 : r.right > box.right + 0.5;
      });
      if (k <= 0) return;                                 // everything fits (or nothing does): leave it alone
      const r = pills[k].getBoundingClientRect();
      const shown = rtl ? r.right - box.left : box.right - r.left;
      const target = Math.min(r.width * MAX_SHOWN, Math.max(r.width * MIN_SHOWN, MIN_SHOWN_PX));
      if (Math.abs(shown - target) <= TOLERANCE) return;
      // Each of the k pills before it grows by 2·d on its two sides, which moves the cut pill by 2·d·k
      // (it grows by 2·d itself too, which the tolerance absorbs). Solve shown - 2dk = target for d.
      const d = (shown - target) / (2 * k);
      row.style.setProperty('--peek-shift', `${Math.max(-MAX_SHIFT, Math.min(MAX_SHIFT, d)).toFixed(1)}px`);
    };

    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(row);
    void document.fonts?.ready.then(fit);                // pill widths change once the web font arrives
    return () => ro.disconnect();
  }, [rowRef, active]);
}
