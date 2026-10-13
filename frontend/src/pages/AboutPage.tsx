import { useDocumentTitle } from '../lib/useDocumentTitle';

const SCRAPER_REPO = 'https://github.com/OpenIsraeliSupermarkets/israeli-supermarket-scarpers';
const PARSER_REPO = 'https://github.com/OpenIsraeliSupermarkets/israeli-supermarket-parsers';
const FEEDBACK = 'https://github.com/liabenyehonatan/supermarket-prices/issues';

/** About, disclaimer, privacy and credits: the "small print" a public price site needs. */
export function AboutPage() {
  useDocumentTitle('אודות והבהרות | סלי');
  return (
    <div className="page-wrapper">
      <div className="container about-page">
        <h1>אודות והבהרות</h1>

        <h2>מה זה סלי</h2>
        <p>סלי משווה מחירי סופרמרקט בין רשתות בישראל: מחפשים מוצר או בונים סל קניות ורואים איפה הכי זול.</p>

        <h2>מאיפה המחירים</h2>
        <p>
          המחירים מגיעים מקבצי המחירים הציבוריים שהרשתות מחויבות לפרסם לפי החוק, ומתעדכנים פעמיים ביום.
          סלי אינו קשור לרשתות ואינו מטעמן.
        </p>
        <p>
          <strong>המחירים להמחשה והשוואה בלבד.</strong> ייתכנו הבדלים בין המחיר כאן למחיר בחנות או באתר הרשת:
          מבצעים, מחירי מועדון, שינויי מחיר שנעשו אחרי העדכון האחרון, מוצרים שאזלו, וטעויות בקבצים שהרשתות מפרסמות.
          אין באתר התחייבות לדיוק או לזמינות. לפני רכישה כדאי לוודא את המחיר בחנות.
        </p>

        <h2>פרטיות</h2>
        <ul>
          <li>אין הרשמה, אין עוגיות ואין מעקב או ניתוח התנהגות.</li>
          <li>הסלים שלך נשמרים רק בדפדפן שלך (אחסון מקומי) ולא נשלחים אלינו.</li>
          <li>
            המיקום נשאר במכשיר. כדי לזהות את העיר נשלחת לשרת שלנו נקודה מעוגלת (כקילומטר) והיא לא נשמרת.
            אפשר גם לבחור עיר ידנית.
          </li>
          <li>המצלמה משמשת לסריקת ברקוד בלבד. התמונה נשארת במכשיר.</li>
        </ul>

        <h2>קרדיטים</h2>
        <p>
          אוסף קבצי המחירים ופענוחם נעשים בעזרת הפרויקטים הפתוחים{' '}
          <a href={SCRAPER_REPO} target="_blank" rel="noopener noreferrer">israeli-supermarket-scarpers</a> ו־
          <a href={PARSER_REPO} target="_blank" rel="noopener noreferrer">israeli-supermarket-parsers</a>{' '}
          מאת Sefi Erlich (OpenIsraeliSupermarkets), ברישיון לשימוש לא מסחרי. נעשו בהם התאמות לצורכי האתר.
        </p>
        <p>
          תמונות המוצרים מגיעות מהקטלוג הציבורי של שופרסל אונליין, והלוגואים שייכים לרשתות. כולם שייכים לבעליהם.
        </p>

        <h2>דיווח על שגיאה</h2>
        <p>
          מצאת מחיר שגוי או תקלה? אפשר לדווח{' '}
          <a href={FEEDBACK} target="_blank" rel="noopener noreferrer">כאן</a>.
        </p>
      </div>
    </div>
  );
}
