import { cleanBrand, extractProductDisplay, fixProductName } from './utils';
import { money } from './safe';

// Small decisions about what a product card says beside the price.

const UNIT_WORDS: [RegExp, string][] = [
  [/^(ק"ג|ק״ג|קג|קילו|קילוגרם)$/, 'ק״ג'],
  [/^(גרם|גר'|גר|ג'|ג)$/, 'גרם'],
  [/^(מ"ל|מ״ל|מל'|מל|מיליליטר)$/, 'מ״ל'],
  [/^(ליטר|ל'|ל)$/, 'ליטר'],
];

/**
 * { price: "₪2.04", per: "ל-100 גרם" }, or null when it would mislead or say nothing new (the two parts are kept
 * apart so the page can keep "₪2.04" left-to-right inside Hebrew text).
 * The chains report the price per their unit of measure. Only weights and volumes are compared: for "יחידות"
 * the chains put the whole pack's price there, not a per-item one. A pack that is exactly one unit (1 litre of milk)
 * has a unit price equal to its price, which adds nothing.
 */
export function unitPriceLabel(price: unknown, unitPrice: unknown, unit?: string | null): { price: string; per: string } | null {
  const p = Number(price), u = Number(unitPrice);
  if (!unit || !Number.isFinite(p) || !Number.isFinite(u) || u <= 0 || Math.abs(u - p) < 0.005) return null;
  const m = fixProductName(unit).trim().match(/^(\d+(?:\.\d+)?)?\s*(.+)$/);
  if (!m) return null;
  const word = UNIT_WORDS.find(([re]) => re.test(m[2].trim()))?.[1];
  if (!word) return null;
  const qty = m[1] && Number(m[1]) !== 1 ? m[1] : '';
  return { price: money(u), per: qty ? `ל-${qty} ${word}` : `ל${word}` };
}

const SIZE_PARTS = /^(\d+(?:[.,]\d+)?)(?:\s*[×*x]\s*(\d+(?:[.,]\d+)?))?\s*(גרם|ק"ג|ק״ג|קילוגרם|ליטר|מ"ל|מ״ל|מיליליטר|יחידות|יחידה)$/;

/**
 * The price per 100 g / per kg, per 100 ml / per litre, or per item, worked out from the pack's own size ("250 גרם",
 * "6×1.5 ליטר", "12 יחידות") and the price, so every product with a readable size gets one in the same units
 * (the chains' own unit prices are missing for many products, and odd for some). Null when the size cannot be read,
 * when the pack is exactly one kilo / litre / item (nothing new to say), or when the result looks implausible.
 */
export function sizeUnitPrice(price: unknown, name?: string | null, brand?: string | null, unit?: string | null): { price: string; per: string } | null {
  const p = Number(price);
  if (!Number.isFinite(p) || p <= 0 || !name) return null;
  const { size } = extractProductDisplay(name, brand, unit);
  const m = fixProductName(size).trim().match(SIZE_PARTS);
  if (!m) return null;
  const amount = Number(m[1].replace(',', '.')) * (m[2] ? Number(m[2].replace(',', '.')) : 1);
  if (!Number.isFinite(amount) || amount <= 0) return null;
  const word = m[3];
  let value: number, per: string;
  if (/^(גרם|ק)/.test(word) || word === 'קילוגרם') {
    const grams = /^(ק"ג|ק״ג|קילוגרם)$/.test(word) ? amount * 1000 : amount;
    if (grams < 5 || grams > 50000) return null;
    if (grams >= 1000) { value = p / (grams / 1000); per = 'לק״ג'; } else { value = (p / grams) * 100; per = 'ל-100 גרם'; }
  } else if (/^(ליטר|מ"ל|מ״ל|מיליליטר)$/.test(word)) {
    const ml = word === 'ליטר' ? amount * 1000 : amount;
    if (ml < 5 || ml > 50000) return null;
    if (ml >= 1000) { value = p / (ml / 1000); per = 'לליטר'; } else { value = (p / ml) * 100; per = 'ל-100 מ״ל'; }
  } else {
    if (amount < 2 || amount > 1000) return null;                 // a single item: the price is the unit price
    value = p / amount; per = 'ליחידה';
  }
  if (value < 0.01 || Math.abs(value - p) < 0.005) return null;
  return { price: money(value), per };
}

// Words that describe the kind of company, not its name ("מאפיית אנג'ל" is Angel)
const COMPANY_WORDS = /^(מאפיית|מאפיות|מחלבת|מחלבות|חברת|קבוצת|תעשיות|מפעלי|משק|יקב|מבשלת)$/;
const norm = (s: string) => s.replace(/[׳'"״`.\-]/g, '').trim();

/**
 * The brand to show under a product name, or '' when the name already says it. "מאפיית שלמה א. אנג'ל" beside
 * "לחם אנג'ל חיטה מלאה" repeats Angel; beside a name without it, it becomes "שלמה אנג'ל".
 */
export function brandForCard(name: string, brand?: string | null): string {
  const clean = cleanBrand(brand);
  if (!clean || clean === '---') return '';
  // Without company-kind words and lone initials ("שלמה א. אנג'ל" → "שלמה אנג'ל")
  const words = clean.split(/\s+/).filter(w => !COMPANY_WORDS.test(w) && !/^[\u05D0-\u05EA]['׳.]?$/.test(w));
  const nameNorm = norm(name);
  if (words.some(w => norm(w).length >= 3 && nameNorm.includes(norm(w)))) return '';
  return words.join(' ');
}
