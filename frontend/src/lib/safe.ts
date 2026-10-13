// Small safety helpers shared by pages.

/** The URL if it is a plain http(s) link, otherwise null (never render javascript:/data: links). */
export function safeHttpUrl(url?: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** "₪12.50" for any value the API sends; a dash instead of "₪NaN" when it is missing. */
export function money(value: unknown): string {
  const n = Number(value);
  if (value === null || value === undefined || value === '' || !Number.isFinite(n)) return '–';
  return `₪${n.toFixed(2)}`;
}
