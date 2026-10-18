import { Fragment, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigationType } from 'react-router-dom';
import { fetchDeals, type Deal } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { Search, X } from 'lucide-react';
import { ChainCarousel } from '../components/ChainCarousel';
import { DealCard } from '../components/DealCard';
import { DealProductsSheet } from '../components/DealProductsSheet';
import { DealsRulesBox } from '../components/DealsRulesBox';
import { ErrorState } from '../components/ErrorState';
import { readDealsSnapshot, writeDealsSnapshot } from '../lib/dealsSnapshot';
import { hasSeen, markSeen } from '../lib/firstVisit';
import { onCityFilterChange, readCityFilter } from '../lib/filters';
import { useDocumentTitle } from '../lib/useDocumentTitle';

const PAGE = 24;
const hasPicture = (d: Deal) => d.sample_products.some(p => p.image_url);
const INTRO_KEY = 'sali_deals_intro_seen';

const filterKey = (f: { chain: string; city: string; sort: string; kind: string; q: string }) => `${f.chain}|${f.city}|${f.sort}|${f.kind}|${f.q}`;

export function DealsPage() {
  useDocumentTitle('מבצעים | סלי');
  const { addItem } = useBasket();
  const [city, setCity] = useState(readCityFilter);
  // Coming back (browser back or the page's back button, a POP) from a product page: the saved view (filters, cards
  // loaded so far, scroll position) is used as is. Arriving by a link or the menu starts from a fresh list.
  const navigationType = useNavigationType();
  const initial = useRef(navigationType === 'POP' ? readDealsSnapshot(readCityFilter()) : null);
  // The filters the saved cards belong to: while they are unchanged nothing is fetched (it must survive React's dev
  // double-run of effects, so it is not a one-shot flag); any real fetch clears it.
  const restoredFor = useRef<string | null>(initial.current && filterKey({ ...initial.current, q: initial.current.q ?? '' }));
  const [chain, setChain] = useState(initial.current?.chain ?? '');
  const [sort, setSort] = useState<'best' | 'ending'>(initial.current?.sort ?? 'best');
  const [kind, setKind] = useState<'' | 'single' | 'group'>(initial.current?.kind ?? '');
  // What is typed in the search box, and (a moment after the typing stops) the words the list is searched for
  const [typed, setTyped] = useState(initial.current?.q ?? '');
  const [q, setQ] = useState(initial.current?.q ?? '');
  useEffect(() => {
    const t = setTimeout(() => setQ(typed.trim()), 350);
    return () => clearTimeout(t);
  }, [typed]);
  // A new search starts at the top of its results (the box stays in view, so it can be changed again at once)
  const firstQ = useRef(true);
  useEffect(() => {
    if (firstQ.current) { firstQ.current = false; return; }
    window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior });
  }, [q]);
  const [deals, setDeals] = useState<Deal[]>(initial.current?.deals ?? []);
  const [total, setTotal] = useState(initial.current?.total ?? 0);
  const [chains, setChains] = useState<{ name: string; count: number }[]>(initial.current?.chains ?? []);
  const [loading, setLoading] = useState(initial.current === null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);   // a later page could not be loaded: the button below offers another try
  const fetched = useRef(initial.current?.deals.length ?? 0);   // how many the server has handed over so far (the next page starts there)
  const sentinel = useRef<HTMLDivElement>(null);
  const [attempt, setAttempt] = useState(0);   // bumped by "try again" to ask for the same list once more
  const [picking, setPicking] = useState<Deal | null>(null);
  // The explanation is for the first visit only: it is on screen with the page, so the visit marks it as seen.
  const [introOpen] = useState(() => !hasSeen(INTRO_KEY));
  useEffect(() => { if (introOpen) markSeen(INTRO_KEY); }, [introOpen]);
  const generation = useRef(0);          // bumped by every filter change: an answer for an older filter is dropped
  const scrollY = useRef(initial.current?.scrollY ?? 0);
  const latest = useRef({ chain, sort, kind, city, q, deals, total, chains });
  latest.current = { chain, sort, kind, city, q, deals, total, chains };

  useEffect(() => onCityFilterChange(setCity), []);

  // Back from a product: put the person where they were (instantly: the site scrolls smoothly otherwise)
  useLayoutEffect(() => {
    // a fresh arrival starts at the top (the page you came from may have been scrolled)
    window.scrollTo({ top: initial.current?.scrollY ?? 0, behavior: 'instant' as ScrollBehavior });
  }, []);

  useEffect(() => {
    if (restoredFor.current === filterKey({ chain, city, sort, kind, q })) return;      // the saved view is already on screen
    restoredFor.current = null;
    let live = true;
    generation.current += 1;
    setLoading(true);
    setLoadingMore(false);
    setLoadFailed(false);
    setMoreFailed(false);
    fetchDeals({ chain, city, sort, kind: kind || undefined, q: q || undefined, limit: PAGE })
      .then(r => { if (live) { fetched.current = r.deals.length; setDeals(r.deals); setTotal(r.total); setChains(r.chains); } })
      .catch(() => { if (live) { setDeals([]); setTotal(0); setLoadFailed(true); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [chain, city, sort, kind, q, attempt]);

  // Keep the view for "back": the data whenever it changes, the scroll position from scroll events (read at leave time
  // it would be mid-animation, or already clamped by the shorter page that replaces this one).
  useEffect(() => {
    if (loading) return;
    writeDealsSnapshot({ ...latest.current, scrollY: scrollY.current });
  }, [loading, chain, sort, kind, city, q, deals, total, chains]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const save = () => writeDealsSnapshot({ ...latest.current, scrollY: scrollY.current });
    const onScroll = () => {
      // The page being left is still listening for a moment while the next one scrolls itself to the top:
      // that scroll must not become the position to come back to
      if (window.location.pathname !== '/promotions') return;
      scrollY.current = window.scrollY;
      if (!timer) timer = setTimeout(() => { timer = null; save(); }, 200);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (timer) clearTimeout(timer);
      save();
    };
  }, []);

  // The carousel lists the brands that have deals now; a chosen brand stays in it even if a city filter empties it
  const chainNames = chains.some(c => c.name === chain) || !chain ? chains.map(c => c.name) : [chain, ...chains.map(c => c.name)];
  const chainCounts = Object.fromEntries(chains.map(c => [c.name, c.count]));

  async function more() {
    if (loadingMore) return;
    const gen = generation.current;
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const r = await fetchDeals({ chain, city, sort, kind: kind || undefined, q: q || undefined, limit: PAGE, offset: fetched.current });
      if (gen !== generation.current) return;          // the filter changed meanwhile: this page belongs to the old one
      fetched.current += r.deals.length;
      setDeals(prev => {
        const seen = new Set(prev.map(d => d.deal_id));
        return [...prev, ...r.deals.filter(d => !seen.has(d.deal_id))];
      });
      // An empty page means the list is at its end (the count can be a little ahead of what can be listed)
      setTotal(r.deals.length === 0 ? fetched.current : r.total);
    } catch {
      if (gen === generation.current) setMoreFailed(true);   // keep what is shown; the button offers another try
    } finally {
      if (gen === generation.current) setLoadingMore(false);
    }
  }

  // The next page loads by itself when the end of the list comes within reach of the scrolling (no button to press).
  // Without IntersectionObserver the button below is all there is.
  const hasMore = !loading && deals.length > 0 && fetched.current < total;
  const moreRef = useRef(more);
  moreRef.current = more;
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore || loadingMore || moreFailed || typeof IntersectionObserver === 'undefined') return;
    const watcher = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) void moreRef.current();
    }, { rootMargin: '900px 0px' });
    watcher.observe(node);
    return () => watcher.disconnect();
  }, [hasMore, loadingMore, moreFailed, deals.length]);
  // The first deal without a picture, when pictured ones came before it: where the small heading goes
  const firstUnpictured = deals.findIndex(d => !hasPicture(d));
  const showDivider = firstUnpictured > 0;

  const add = (deal: Deal, onAdded: () => void) => deal.sample_products[0] && addItem({
    barcode: deal.sample_products[0].barcode, name: deal.sample_products[0].name, brand: deal.sample_products[0].brand,
    unit: deal.sample_products[0].unit_of_measure, quantity: deal.min_qty,
  }, onAdded);

  return (
    <div className="page-wrapper">
      <div className="container">
        <div className="section-header">
          <div>
            <div className="section-title">מבצעים</div>
            <div className="section-subtitle">
              {q
                ? <>{total === 1 ? 'נמצא מבצע אחד' : total === 0 ? 'לא נמצאו מבצעים' : `${total} מבצעים נמצאו`} עבור <bdi>״{q}״</bdi>{city ? ` בסניפי ${city}` : ''}</>
                : <>{total} מבצעים בתוקף{city ? ` בסניפי ${city}` : ''}, מדורגים לפי כמה הם זולים מהמחיר הזול שמצאנו ברשתות</>}
            </div>
          </div>
        </div>

        {introOpen && <DealsRulesBox />}

        <div className="deals-search-bar">
          <label className="chain-search deals-search">
            <Search size={17} strokeWidth={2} aria-hidden />
            <input
              type="search"
              value={typed}
              onChange={e => setTyped(e.target.value)}
              placeholder="חפשו מבצע, מוצר או רשת: עוגיות, חומוס…"
              aria-label="חיפוש במבצעים"
              enterKeyHint="search"
              autoComplete="off"
              maxLength={60}
            />
            {typed && (
              <button type="button" className="deals-search-clear" aria-label="ניקוי החיפוש" onClick={() => { setTyped(''); setQ(''); }}>
                <X size={15} strokeWidth={2.5} />
              </button>
            )}
          </label>
        </div>

        {/* No brand has a deal for these filters: nothing to pick from (its own "no brand found" line would be misleading) */}
        {chainNames.length > 0 && (
          <ChainCarousel
            chains={chainNames}
            counts={chainCounts}
            selected={chain}
            onSelect={name => setChain(chain === name ? '' : name)}
            withSearch={false}
            style={{ marginBottom: 12 }}
          />
        )}
        {chain && (
          <div className="chain-active-note" role="status">
            <span>מבצעים רק מ<strong>{chain}</strong></span>
            <button onClick={() => setChain('')}><X size={13} strokeWidth={2.5} />הציגו את כל הרשתות</button>
          </div>
        )}
        <div className="filter-bar deals-filters" role="group" aria-label="מיון וסוג">
          <button className={`filter-chip${sort === 'best' ? ' active' : ''}`} onClick={() => setSort('best')}>הכי משתלמים</button>
          <button className={`filter-chip${sort === 'ending' ? ' active' : ''}`} onClick={() => setSort('ending')}>נגמרים בקרוב</button>
          <button className={`filter-chip${kind === 'single' ? ' active' : ''}`} onClick={() => setKind(kind === 'single' ? '' : 'single')}>מוצר בודד</button>
          <button className={`filter-chip${kind === 'group' ? ' active' : ''}`} onClick={() => setKind(kind === 'group' ? '' : 'group')}>קבוצת מוצרים</button>
        </div>

        {!loading && loadFailed && (
          <ErrorState text="לא הצלחנו לטעון את המבצעים כרגע. נסו שוב בעוד רגע." onRetry={() => { restoredFor.current = null; setAttempt(n => n + 1); }} compact />
        )}
        {!loading && !loadFailed && deals.length === 0 && (
          <div className="empty-state" style={{ padding: '32px 0' }}>
            {q ? (
              <>
                <div className="empty-state-title">לא נמצאו מבצעים עבור <bdi>״{q}״</bdi></div>
                <div className="empty-state-desc">נסו מילה אחרת (למשל שם של מוצר או סוג מוצר), או הסירו חלק מהסינון</div>
                <button className="btn btn-secondary btn-sm" onClick={() => { setTyped(''); setQ(''); }}>ניקוי החיפוש</button>
              </>
            ) : (
              <div className="empty-state-title">אין כרגע מבצעים שמתאימים לסינון</div>
            )}
          </div>
        )}
        <div className="deals-grid">
          {deals.map((d, i) => (
            <Fragment key={d.deal_id}>
              {showDivider && i === firstUnpictured && (
                <h2 className="deals-divider">מבצעים בלי תמונה</h2>
              )}
              <DealCard deal={d} onPick={setPicking} onAdd={add} />
            </Fragment>
          ))}
        </div>
        <div ref={sentinel} aria-hidden style={{ height: 1 }} />
        {hasMore && (loadingMore
          ? <p className="deals-loading" role="status">טוענים עוד מבצעים…</p>
          : (moreFailed || typeof IntersectionObserver === 'undefined') && (
              <button className="btn btn-secondary btn-full deals-more" onClick={() => void more()}>
                {moreFailed ? 'לא הצלחנו לטעון, נסו שוב' : 'עוד מבצעים'}
              </button>
            ))}
        <p className="deals-footnote">
          המחיר ליחידה מחושב מהמבצע ומושווה למחיר המדף הזול ביותר שמצאנו. מבצעי מועדון וקופונים לא מוצגים.
        </p>
      </div>
      {picking && <DealProductsSheet deal={picking} onClose={() => setPicking(null)} />}
    </div>
  );
}
