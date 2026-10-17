import { cleanBrand, fixProductName } from './utils';
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
