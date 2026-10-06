export function cn(...inputs: (string | undefined | null | false | 0)[]) {
  return inputs.filter(Boolean).join(' ');
}

// Strip corporate suffixes like בע"מ, (ישראל), Ltd from brand/manufacturer names
const CORP_SUFFIXES = /[\s,]+(?:בע[""״]מ|בעמ|ישראל בע[""״]מ|ישראל|\(ישראל\)|ltd\.?|limited|לימיטד)[\s,.]*/gi;

export function cleanBrand(name?: string | null): string {
  if (!name) return '';
  return name.replace(CORP_SUFFIXES, '').trim();
}

// Filter out unit_of_measure values that are price-comparison bases (100g/100ml),
// not actual package sizes. Keep "1 ליטר", "1 קילוגרם", "יחידות" etc.
export function displayUnit(unit?: string | null): string {
  if (!unit || unit === '---') return '';
  const fixed = fixProductName(unit);
  // "100 גרם", "100 מיליליטר", "100 מ\"ל" are comparison units — not package size
  if (/^100\s/.test(fixed)) return '';
  return fixed;
}

// Common Hebrew abbreviations used by supermarket chains in product names
const HEB_ABBREVS: Record<string, string> = {
  'שוק.':    'שוקולד',
  'שוקו.':   'שוקולד',
  'עוג.':    'עוגה',
  'יוג.':    'יוגורט',
  'סוכ.':    'סוכריות',
  'חט.':     'חטיף',
  'חטיפ.':   'חטיפים',
  'עגבני.':  'עגבניות',
  'יוגור.':  'יוגורט',
  'מינרל.':  'מינרלים',
  'בק.':     'בקבוק',
  'עגב.':    'עגבניות',
  'עגבנ.':   'עגבניות',
  'מלפפ.':   'מלפפון',
  'פריכ.':   'פריכיות',
  'תער.':    'תערובת',
  'גב.':     'גבינה',
  'דאו.':    'דאודורנט',
  'קפס.':    'קפסולות',
  'מינ.':    'מיני',
  'ללתס':    'ללא תוספת סוכר',
};
const ABBREV_RE = new RegExp(
  Object.keys(HEB_ABBREVS).map(k => k.replace('.', '\\.')).join('|'),
  'g'
);

// Add missing spaces between digits and Hebrew letters in product names
// e.g. "30גרם" → "30 גרם", "חלב3%" → "חלב 3%"
export function fixProductName(name?: string | null): string {
  if (!name) return '';
  return name
    .replace(ABBREV_RE, (m, offset, str) => {
      const expanded = HEB_ABBREVS[m] ?? m;
      const prev = str[offset - 1];
      const next = str[offset + m.length];
      const prefix = prev && prev !== ' ' ? ' ' : '';
      const suffix = next && next !== ' ' ? ' ' : '';
      return prefix + expanded + suffix;
    })
    .replace(/(\d)([א-ת])/g, '$1 $2')
    .replace(/([א-ת])(\d)/g, '$1 $2')
    // "3%בקבוק" → "3% בקבוק": space between % and Hebrew
    .replace(/(%)([א-ת])/g, '$1 $2')
    // "1%1 בקבוק" → "1% בקבוק": remove lone digit glued right after % (formatting artifact)
    .replace(/(\d%)(\d)(?=\s|$)/g, '$1');
}


// Unit words that should NOT be stripped when they follow a number
const UNIT_WORDS = /^(?:גרם|גר'?|מיליליטר|מ["״]?ל|מל|ליטר|ל'|ל|קילוגרם|ק["״]?ג|קג|ג'|ג|יח'?|יחידות|יחידה)$/i;

// Matches "NUMBER unit" at end of a name, e.g. "250 גרם", "1.5 ל'", "500 מל".
// Anything after the unit that is only Hebrew words is captured as a trailing tail
// (usually the brand, e.g. "800 ג יכין" → size "800 גרם", tail "יכין").
// Multipacks ("400*3ג", "6*1.5ל") are kept as one size: "400×3 גרם", "6×1.5 ליטר"
const SIZE_AT_END = /\s+(\d+(?:[.,]\d+)?(?:\s*\*\s*\d+(?:[.,]\d+)?)?)\s*(גרם|גר'?|מיליליטר|מ["״]?ל|מל|ליטר|ל'|ל|קילוגרם|ק["״]?ג|קג|ג'|ג|יח'|יחידות|יח)((?:\s+[א-ת'"״A-Za-z]+)*)\s*$/;

// Abbreviated units → full words, so the size reads "800 גרם" not "800 ג"
const FULL_UNIT: Record<string, string> = {
  'ג': 'גרם', "ג'": 'גרם', 'גר': 'גרם', "גר'": 'גרם',
  'ל': 'ליטר', "ל'": 'ליטר',
  'מל': 'מ"ל', 'מ"ל': 'מ"ל', 'מ״ל': 'מ"ל', 'מיליליטר': 'מ"ל',
  'קג': 'ק"ג', 'ק"ג': 'ק"ג', 'ק״ג': 'ק"ג', 'קילוגרם': 'ק"ג',
  "יח'": 'יחידות', 'יח': 'יחידות',
};
function fullUnit(unit: string): string {
  return FULL_UNIT[unit] ?? unit;
}

// Multipack separator "*" shown as "×"
function fullNumber(num: string): string {
  return num.replace(/\s*\*\s*/, '×');
}

function _stripBrandAndJunk(workingName: string, brand?: string | null): string {
  let result = workingName;
  if (brand) {
    const cleanedBrand = cleanBrand(brand).trim();
    if (cleanedBrand && result.endsWith(cleanedBrand)) {
      result = result.slice(0, result.length - cleanedBrand.length).trim();
    }
  }
  // Strip "NUMBER non-unit-word" at end (e.g. "185 רושן" — brand in different script)
  result = result.replace(/\s+\d+(\.\d+)?\s+(\S+)\s*$/, (_m, _d, word) =>
    UNIT_WORDS.test(word) ? _m : ''
  ).trim();
  return result;
}

/**
 * Returns { displayName, size } for the new display format:
 *   "חלב 1% בקרטון, 1 ליטר"   displayName="חלב 1% בקרטון"  size="1 ליטר"
 *   "תפוצ׳יפס פופס, 50 גרם"   displayName="תפוצ׳יפס פופס"  size="50 גרם"
 *   "ביצים גדולות"             displayName="ביצים גדולות"   size=""
 */
export function extractProductDisplay(
  name?: string | null,
  brand?: string | null,
  unit?: string | null,
): { displayName: string; size: string; tailBrand: string } {
  if (!name) return { displayName: '', size: '', tailBrand: '' };

  let workingName = fixProductName(name);
  workingName = _stripBrandAndJunk(workingName, brand);

  // Check unit_of_measure for a real package size (not comparison unit "100 X")
  if (unit && unit !== '---') {
    const fixedUnit = fixProductName(unit);
    const isMeasure = /(גרם|ליטר|מ"ל|ק"ג|קילוגרם)/.test(fixedUnit);
    if (!/^100\s/.test(fixedUnit) && isMeasure) {
      // Real size from unit_of_measure — strip SIZE + any trailing Hebrew-only words (e.g. partial brand)
      // e.g. "חלב מועשר 1% בקבוק 1 ל יטבתה" → strip " 1 ל יטבתה" → "חלב מועשר 1% בקבוק"
      const sizeMatch = workingName.match(SIZE_AT_END);
      const nameWithoutSize = sizeMatch
        ? workingName.slice(0, sizeMatch.index).trim()
        : workingName;
      return {
        displayName: nameWithoutSize || workingName,
        size: fixedUnit,
        tailBrand: sizeMatch?.[3]?.trim() ?? '',
      };
    }
  }

  // unit_of_measure is comparison-only ("100 גרם") or absent — extract size from name
  const sizeMatch = workingName.match(SIZE_AT_END);
  if (sizeMatch) {
    const nameWithoutSize = workingName.slice(0, sizeMatch.index).trim();
    return {
      displayName: nameWithoutSize || workingName,
      size: fullNumber(sizeMatch[1]) + ' ' + fullUnit(sizeMatch[2]),
      tailBrand: sizeMatch[3]?.trim() ?? '',
    };
  }

  // No size found — strip trailing bare number
  workingName = workingName.replace(/\s+\d+(\.\d+)?\s*$/, '').trim();
  return { displayName: workingName || fixProductName(name), size: '', tailBrand: '' };
}

export function cleanProductName(name?: string | null, brand?: string | null): string {
  const { displayName, size } = extractProductDisplay(name, brand);
  return size ? `${displayName}, ${size}` : displayName;
}
