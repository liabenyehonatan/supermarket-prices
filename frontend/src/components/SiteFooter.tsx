import { Link } from 'react-router-dom';

/** A quiet line at the bottom of every page: the disclaimer and credits live one tap away. */
export function SiteFooter() {
  return (
    <footer className="site-footer">
      <Link to="/about">אודות והבהרות</Link>
      <span aria-hidden> · </span>
      <span>המחירים להמחשה בלבד</span>
    </footer>
  );
}
