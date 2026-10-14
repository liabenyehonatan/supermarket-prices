import { ShieldCheck } from 'lucide-react';
import type { DealRules } from '../api/client';

const pct = (fraction: number | string) => Math.round(Number(fraction) * 100);

/** Shown once, the first time someone opens the promotions page: why this list is short. The numbers come from the API. */
export function DealsRulesBox({ rules }: { rules: DealRules }) {
  return (
    <section className="deals-rules" aria-label="איך אנחנו בוחרים מבצעים">
      <ShieldCheck size={20} strokeWidth={2} aria-hidden="true" />
      <p>
        <strong>לא סתם מבצעים.</strong> מציגים רק מבצע שחוסך לפחות <bdi>{pct(rules.min_saving)}%</bdi> מהמחיר הזול ביותר
        שמצאנו ברשתות, ומסתירים &quot;הנחות&quot; שנראות טוב מדי (מעל <bdi>{pct(rules.max_saving)}%</bdi>), כי לרוב זו טעות בנתונים.
      </p>
    </section>
  );
}
