import { Link } from 'react-router-dom';
import { useDocumentTitle, useNoIndex } from '../lib/useDocumentTitle';

/** An address that is not a page. (The server answers such addresses with a real 404 as well.) */
export function NotFoundPage() {
  useDocumentTitle('הדף לא נמצא | סלי');
  useNoIndex();
  return (
    <div className="page-wrapper">
      <div className="container about-page">
        <h1>הדף לא נמצא</h1>
        <p>הכתובת הזאת לא קיימת באתר.</p>
        <p><Link to="/">חזרה לחיפוש מוצר</Link> · <Link to="/promotions">מבצעים</Link></p>
      </div>
    </div>
  );
}
