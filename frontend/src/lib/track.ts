// Visitor statistics. One call, `track(...)`, feeds two places:
//   1. the site's own anonymous statistics (POST /api/v1/events, read on the /stats page), and
//   2. Google Analytics 4, only when a measurement ID is configured (GA_MEASUREMENT_ID in .env).
// Never throws and never blocks the page: statistics are not worth breaking a search for.

export type TrackEvent =
  | 'page_view' | 'click' | 'time'
  | 'search' | 'product_open' | 'basket_add' | 'basket_compare' | 'scan' | 'deal_open';

interface Payload { event: TrackEvent; path: string; label?: string; value?: number }

const ENDPOINT = `${import.meta.env.VITE_API_URL ?? ''}/api/v1/events`;
const GA_ID_PATTERN = /^G-[A-Z0-9]{4,16}$/;

function uuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

function stored(storage: 'localStorage' | 'sessionStorage', key: string): string {
  try {
    const s = window[storage];
    let v = s.getItem(key);
    if (!v) { v = uuid(); s.setItem(key, v); }
    return v;
  } catch { return uuid(); }   // storage blocked: this page load counts as its own visitor
}

const visitorId = () => stored('localStorage', 'sali.visitor');
const sessionId = () => stored('sessionStorage', 'sali.session');

/** Where the visit came from: ?utm_source=… or ?src=… on the landing address, remembered for the session. */
function source(): string | undefined {
  try {
    const p = new URLSearchParams(window.location.search);
    const s = (p.get('utm_source') || p.get('src') || '').trim().toLowerCase();
    if (s) sessionStorage.setItem('sali.source', s);
    return sessionStorage.getItem('sali.source') || undefined;
  } catch { return undefined; }
}

// ── Our own statistics ───────────────────────────────────────────────────────

let queue: Payload[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function flush() {
  if (timer) { clearTimeout(timer); timer = null; }
  if (!queue.length) return;
  const events = queue.splice(0, 50);
  const body = JSON.stringify({ visitor_id: visitorId(), session_id: sessionId(), source: source(), events });
  try {
    // sendBeacon survives the page closing; fetch keepalive is the fallback
    const blob = new Blob([body], { type: 'application/json' });
    if (!(navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, blob))) {
      void fetch(ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body, keepalive: true }).catch(() => {});
    }
  } catch { /* statistics are best effort */ }
  if (queue.length) flush();
}

// ── Google Analytics 4 ───────────────────────────────────────────────────────

type Gtag = (...args: unknown[]) => void;
let gaReady = false;

function gaId(): string | null {
  const id = document.querySelector('meta[name="ga-measurement-id"]')?.getAttribute('content')?.trim() ?? '';
  return GA_ID_PATTERN.test(id) ? id : null;   // the placeholder is removed at start-up when no ID is set
}

function initGa() {
  const id = gaId();
  if (!id || gaReady) return;
  gaReady = true;
  const w = window as unknown as { dataLayer: unknown[]; gtag: Gtag };
  w.dataLayer = w.dataLayer || [];
  w.gtag = function gtag() { w.dataLayer.push(arguments); };   // gtag.js needs the real `arguments` object
  w.gtag('js', new Date());
  w.gtag('config', id, {
    send_page_view: false,                   // the router reports page views itself (single-page app)
    allow_google_signals: false,             // no cross-device / advertising profiles
    allow_ad_personalization_signals: false,
  });
  const s = document.createElement('script');
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`;
  document.head.appendChild(s);
}

/** Our event names, in Google's vocabulary where one exists, so GA4's standard reports understand them. */
function sendToGa(e: Payload) {
  if (!gaReady) return;
  const gtag = (window as unknown as { gtag: Gtag }).gtag;
  const item = e.label ? [{ item_id: e.label }] : undefined;
  switch (e.event) {
    case 'page_view':      gtag('event', 'page_view', { page_path: e.path, page_location: window.location.href, page_title: document.title }); break;
    case 'search':         gtag('event', 'search', { search_term: e.label }); break;
    case 'product_open':   gtag('event', 'view_item', { items: item }); break;
    case 'basket_add':     gtag('event', 'add_to_cart', { items: item }); break;
    case 'basket_compare': gtag('event', 'basket_compare', { item_count: e.value }); break;
    case 'scan':           gtag('event', 'barcode_scan', { result: e.label }); break;
    case 'deal_open':      gtag('event', 'select_promotion', { promotion_name: e.label }); break;
    case 'click':          gtag('event', 'outbound_click', { link_type: e.label }); break;
    case 'time':           break;   // GA measures engagement time by itself
  }
}

// ── Public API ───────────────────────────────────────────────────────────────

export function track(event: TrackEvent, extra: { label?: string; value?: number } = {}) {
  try {
    if (typeof window === 'undefined') return;
    const payload: Payload = { event, path: window.location.pathname, ...extra };
    queue.push(payload);
    if (queue.length >= 20) flush(); else if (!timer) timer = setTimeout(flush, 2000);
    sendToGa(payload);
  } catch { /* never let statistics break the page */ }
}

/** Seconds the page was visible, reported when the visitor leaves or switches away. */
let visibleSince = 0;
let started = false;

export function startTracking() {
  if (started || typeof window === 'undefined') return;
  started = true;
  try {
    initGa();
    visibleSince = document.visibilityState === 'visible' ? Date.now() : 0;
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        if (visibleSince) {
          const seconds = Math.round((Date.now() - visibleSince) / 1000);
          visibleSince = 0;
          if (seconds > 0) track('time', { value: Math.min(seconds, 3600) });
        }
        flush();
      } else {
        visibleSince = Date.now();
      }
    });
    window.addEventListener('pagehide', flush);
  } catch { /* best effort */ }
}
