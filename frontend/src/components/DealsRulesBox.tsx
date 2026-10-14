import { ShieldCheck } from 'lucide-react';

/** Shown once, the first time someone opens the promotions page: what makes this list different from "any promotion". */
export function DealsRulesBox() {
  return (
    <section className="deals-rules" aria-label="איך אנחנו בוחרים מבצעים">
      <ShieldCheck size={20} strokeWidth={2} aria-hidden="true" />
      <p>
        <strong>לא סתם מבצעים.</strong> מחשבים את המחיר ליחידה במבצע ומשווים אותו למחיר הזול ביותר שכבר מצאנו
        על המדף לאותו מוצר, ומציגים רק מבצעים שבאמת יוצאים זולים יותר, לא כל מבצע שקיים ברשתות.
      </p>
    </section>
  );
}
