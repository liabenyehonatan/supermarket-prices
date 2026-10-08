import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { fetchStats, type DataStats } from '../api/client';

function whenUpdated(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  const hhmm = d.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', hour12: false });
  if (days < 1 && new Date().getDate() === d.getDate()) return `עודכן היום ב-${hhmm}`;
  if (days <= 1) return 'עודכן אתמול';
  if (days < 30) return `עודכן לפני ${days} ימים`;
  return `עודכן לפני ${Math.floor(days / 30) === 1 ? 'חודש' : `${Math.floor(days / 30)} חודשים`}`;
}

function compactCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')} מיליון`;
  if (n >= 10_000) return `${Math.floor(n / 1000)} אלף`;
  return n.toLocaleString('he-IL');
}

/** Under the search field: how fresh and how broad the data is — the reason to trust the prices. */
export function TrustLine() {
  const [stats, setStats] = useState<DataStats | null>(null);
  useEffect(() => { fetchStats().then(setStats).catch(() => {}); }, []);

  const parts = stats
    ? [
        stats.last_updated ? whenUpdated(stats.last_updated) : '',
        stats.chains === 1 ? 'רשת אחת' : `${stats.chains} רשתות`,
        `${compactCount(stats.products)} מוצרים`,
      ].filter(Boolean)
    : ['מחירים מעודכנים מכל הרשתות'];

  return (
    <p className="trust-line">
      <RefreshCw size={13} strokeWidth={2} aria-hidden />
      {parts.join(' · ')}
    </p>
  );
}
