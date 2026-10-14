import { ShieldCheck } from 'lucide-react';
import type { DealRules } from '../api/client';

const pct = (fraction: number | string) => Math.round(Number(fraction) * 100);

/** Tells shoppers why this list is short: a promotion is shown only if it is really cheap. The numbers come from the API. */
export function DealsRulesBox({ rules }: { rules: DealRules }) {
  return (
    <section className="deals-rules" aria-label="איך אנחנו בוחרים מבצעים">
      <div className="deals-rules-head">
        <ShieldCheck size={20} strokeWidth={2} aria-hidden="true" />
        <strong>לא סתם מבצעים: מציגים רק מה שבאמת זול</strong>
      </div>
      <ul>
        <li>מחשבים כמה עולה יחידה אחת במבצע, ומשווים למחיר הזול ביותר שמצאנו לאותו מוצר ברשתות.</li>
        <li>מציגים רק מבצע שחוסך לפחות <bdi>{pct(rules.min_saving)}%</bdi> לעומת המחיר הזה.</li>
        <li>
          מבצע שנראה טוב מדי (יותר מ-<bdi>{pct(rules.max_saving)}%</bdi> הנחה) לא מוצג, כי ברוב המקרים זו טעות בנתונים של הרשת.
        </li>
        <li>
          לא משווים למחיר סמלי (פחות מ-<bdi>₪{Number(rules.min_reference_price).toFixed(2)}</bdi>), ולא מציגים מבצעי מועדון וקופונים.
        </li>
        <li>רק מבצעים שבתוקף היום, מרשתות שהנתונים שלהן עדכניים.</li>
      </ul>
    </section>
  );
}
