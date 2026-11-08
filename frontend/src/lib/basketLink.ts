// The "open this basket on the site" link that Claude (through the MCP connector) hands to a shopper:
//   /basket?items=<barcode>:<qty>,<barcode>:<qty>
// Anything in it is untrusted text from the address bar: it is validated here and never throws.

export interface LinkItem { barcode: string; quantity: number }

const MAX_ENTRIES = 100;   // same as the API's limit for one basket
const MAX_LINE_QTY = 99;   // a basket line is 1 to 99

/** The valid items of a query string's `items` parameter, in the order given. Entries that are not
 *  `digits:quantity` (barcode of 1 to 20 digits, whole quantity 1 to 99) are skipped; a barcode listed twice has its
 *  quantities added (up to 99). Only the first 100 entries are read. */
export function parseBasketLink(search: string): LinkItem[] {
  try {
    const raw = new URLSearchParams(search).get('items');
    if (!raw) return [];
    const merged = new Map<string, number>();
    for (const entry of raw.split(',').slice(0, MAX_ENTRIES)) {
      const parts = entry.split(':');
      if (parts.length !== 2) continue;
      const [barcode, qty] = parts;
      if (!/^\d{1,20}$/.test(barcode) || !/^\d{1,3}$/.test(qty)) continue;
      const n = Number(qty);
      if (n < 1 || n > MAX_LINE_QTY) continue;
      merged.set(barcode, Math.min(MAX_LINE_QTY, (merged.get(barcode) ?? 0) + n));
    }
    return [...merged].map(([barcode, quantity]) => ({ barcode, quantity }));
  } catch {
    return [];
  }
}
