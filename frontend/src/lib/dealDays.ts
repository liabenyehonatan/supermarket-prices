/** The calendar day in Israel as a day number, so "tonight" and "tomorrow" do not depend on the viewer's time zone. */
function israelDay(d: Date): number {
  const [y, m, day] = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Jerusalem', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(d).split('-').map(Number);
  return Math.round(Date.UTC(y, m - 1, day) / 86400000);
}

/** Whole calendar days from `now` until the promotion's last day (0 = it ends today). */
export function daysLeft(endsAtIso: string, now: Date = new Date()): number {
  return israelDay(new Date(endsAtIso)) - israelDay(now);
}

/** "Ends tomorrow", "ends in 3 days": the promotions' end as a short line; null when it is far off (over `within` days) or unknown. */
export function endsText(iso?: string | null, within = 14): string | null {
  if (!iso) return null;
  const days = daysLeft(iso);
  if (days < 0) return null;
  if (days === 0) return 'נגמר היום';
  if (days === 1) return 'נגמר מחר';
  return days <= within ? `נגמר בעוד ${days} ימים` : null;
}
