import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigationType } from 'react-router-dom';
import { fetchDeals, type Deal } from '../api/client';
import { useBasket } from '../context/BasketContext';
import { X } from 'lucide-react';
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
const INTRO_KEY = 'sali_deals_intro_seen';

const filterKey = (f: { chain: string; city: string; sort: string; kind: string }) => `${f.chain}|${f.city}|${f.sort}|${f.kind}`;

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
  const restoredFor = useRef<string | null>(initial.current && filterKey(initial.current));
  const [chain, setChain] = useState(initial.current?.chain ?? '');
  const [sort, setSort] = useState<'best' | 'ending'>(initial.current?.sort ?? 'best');
  const [kind, setKind] = useState<'' | 'single' | 'group'>(initial.current?.kind ?? '');
  const [deals, setDeals] = useState<Deal[]>(initial.current?.deals ?? []);
  const [total, setTotal] = useState(initial.current?.total ?? 0);
  const [chains, setChains] = useState<{ name: string; count: number }[]>(initial.current?.chains ?? []);
  const [loading, setLoading] = useState(initial.current === null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);   // bumped by "try again" to ask for the same list once more
  const [picking, setPicking] = useState<Deal | null>(null);
  // The explanation is for the first visit only: it is on screen with the page, so the visit marks it as seen.
  const [introOpen] = useState(() => !hasSeen(INTRO_KEY));
  useEffect(() => { if (introOpen) markSeen(INTRO_KEY); }, [introOpen]);
  const generation = useRef(0);          // bumped by every filter change: an answer for an older filter is dropped
  const scrollY = useRef(initial.current?.scrollY ?? 0);
  const latest = useRef({ chain, sort, kind, city, deals, total, chains });
  latest.current = { chain, sort, kind, city, deals, total, chains };

  useEffect(() => onCityFilterChange(setCity), []);

  // Back from a product: put the person where they were (instantly: the site scrolls smoothly otherwise)
  useLayoutEffect(() => {
    // a fresh arrival starts at the top (the page you came from may have been scrolled)
    window.scrollTo({ top: initial.current?.scrollY ?? 0, behavior: 'instant' as ScrollBehavior });
  }, []);

  useEffect(() => {
    if (restoredFor.current === filterKey({ chain, city, sort, kind })) return;      // the saved view is already on screen
    restoredFor.current = null;
    let live = true;
    generation.current += 1;
    setLoading(true);
    setLoadingMore(false);
    setLoadFailed(false);
    fetchDeals({ chain, city, sort, kind: kind || undefined, limit: PAGE })
      .then(r => { if (live) { setDeals(r.deals); setTotal(r.total); setChains(r.chains); } })
      .catch(() => { if (live) { setDeals([]); setTotal(0); setLoadFailed(true); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [chain, city, sort, kind, attempt]);

  // Keep the view for "back": the data whenever it changes, the scroll position from scroll events (read at leave time
  // it would be mid-animation, or already clamped by the shorter page that replaces this one).
  useEffect(() => {
    if (loading) return;
    writeDealsSnapshot({ ...latest.current, scrollY: scrollY.current });
  }, [loading, chain, sort, kind, city, deals, total, chains]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const save = () => writeDealsSnapshot({ ...latest.current, scrollY: scrollY.current });
    const onScroll = () => {
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
    try {
      const r = await fetchDeals({ chain, city, sort, kind: kind || undefined, limit: PAGE, offset: deals.length });
      if (gen !== generation.current) return;          // the filter changed meanwhile: this page belongs to the old one
      setDeals(prev => {
        const seen = new Set(prev.map(d => d.deal_id));
        return [...prev, ...r.deals.filter(d => !seen.has(d.deal_id))];
      });
      setTotal(r.total);
    } catch {
      /* keep what is shown; the button stays so the person can try again */
    } finally {
      if (gen === generation.current) setLoadingMore(false);
    }
  }

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
              {total} מבצעים בתוקף{city ? ` בסניפי ${city}` : ''}, מדורגים לפי כמה הם זולים מהמחיר הזול שמצאנו ברשתות
            </div>
          </div>
        </div>

        {introOpen && <DealsRulesBox />}

        <ChainCarousel
          chains={chainNames}
          counts={chainCounts}
          selected={chain}
          onSelect={name => setChain(chain === name ? '' : name)}
          style={{ marginBottom: 12 }}
        />
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
            <div className="empty-state-title">אין כרגע מבצעים שמתאימים לסינון</div>
          </div>
        )}
        <div className="deals-grid">
          {deals.map(d => <DealCard key={d.deal_id} deal={d} onPick={setPicking} onAdd={add} />)}
        </div>
        {deals.length < total && (
          <button className="btn btn-secondary btn-full deals-more" disabled={loadingMore} onClick={() => void more()}>{loadingMore ? 'טוענים…' : 'עוד מבצעים'}</button>
        )}
        <p className="deals-footnote">
          המחיר ליחידה מחושב מהמבצע ומושווה למחיר המדף הזול ביותר שמצאנו. מבצעי מועדון וקופונים לא מוצגים.
        </p>
      </div>
      {picking && <DealProductsSheet deal={picking} onClose={() => setPicking(null)} />}
    </div>
  );
}
