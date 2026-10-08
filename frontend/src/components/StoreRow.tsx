import { ChevronDown, ChevronUp, Tag } from 'lucide-react';
import { ChainLogo } from './ChainLogo';

function fmt(p: number | string) { return `₪${Number(p).toFixed(2)}`; }

/**
 * One store in a price list. Shared by the product page and the basket results so
 * a store looks and behaves the same everywhere: logo, name + city, price on the
 * left with the "cheapest" badge or the gap to the cheapest under it, tap to expand.
 */
export function StoreRow({
  chain, name, city, warning, price, isCheapest, cheapestLabel = 'הכי זול', diff,
  open, onToggle, banner, children,
}: {
  chain: string;
  name: string;
  city?: string;
  warning?: string;
  price: number | string;
  isCheapest: boolean;
  cheapestLabel?: string;
  diff?: number;
  open: boolean;
  onToggle: () => void;
  /** Optional strip above the row (e.g. "you saved ₪X") */
  banner?: React.ReactNode;
  /** Details shown when the row is expanded */
  children?: React.ReactNode;
}) {
  return (
    <div className={`store-row${isCheapest ? ' cheapest' : ''}`}>
      {banner}
      <button className="store-row-main" onClick={onToggle} aria-expanded={open}>
        <ChainLogo name={chain} size={44} />

        <div className="store-row-info">
          <div className="store-row-name">{name}</div>
          {city && <div className="store-row-sub">{city}</div>}
          {warning && <div className="store-row-sub store-row-warning">{warning}</div>}
        </div>

        <div className="store-row-right">
          <span className="store-row-price tabular">{fmt(price)}</span>
          {isCheapest ? (
            <span className="badge badge-cheapest store-row-badge">
              <Tag size={10} strokeWidth={2.5} />
              {cheapestLabel}
            </span>
          ) : diff != null && diff > 0.01 ? (
            <span className="compare-row-diff tabular">+{fmt(diff)}</span>
          ) : null}
          {open
            ? <ChevronUp size={16} strokeWidth={2} className="store-row-chevron" />
            : <ChevronDown size={16} strokeWidth={2} className="store-row-chevron" />}
        </div>
      </button>
      {open && <div className="store-row-more">{children}</div>}
    </div>
  );
}
