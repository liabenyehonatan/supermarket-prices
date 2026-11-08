import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';
import rtlTextPlugin from '@mapbox/mapbox-gl-rtl-text/mapbox-gl-rtl-text.min.js?url';
import { Locate, MapPin, Navigation, X } from 'lucide-react';
import { ChainLogo } from './ChainLogo';
import { ISRAEL_BOUNDS, MIN_ZOOM, mapStyle } from '../lib/mapStyle';
import { distanceKm } from '../lib/geo';
import { googleMapsLink, isMappable, isOnlineStore, storeSubtitle, wazeLink } from '../lib/store';
import { money } from '../lib/safe';
import { saveMyCoords, type Coords } from '../lib/location';
import { NEAR_KM, pickBest } from '../lib/bestPin';
import type { BasketStoreTotal } from '../types';


const MAX_PINS = 80;                 // pins drawn at once (the cheapest that fit; zooming in shows more)
const PIN_W = 76, PIN_H = 34;        // the pixel box a pin needs, to keep pins from covering each other

let ready = false;
function setup() {
  if (ready) return;
  ready = true;
  maplibregl.addProtocol('pmtiles', new Protocol().tilev4);
  // Hebrew labels need the right-to-left text plugin, otherwise they come out reversed
  maplibregl.setRTLTextPlugin(rtlTextPlugin, true).catch(() => { /* labels fall back to unshaped text */ });
}

function priceText(total: number): string {
  const n = Number(total);
  return `₪${n >= 100 ? Math.round(n).toLocaleString('he-IL') : n.toFixed(1)}`;
}

/**
 * Airbnb-style map of a basket comparison: a price pin on every branch, the cheapest in green, branches that
 * lack some of the basket in grey. `stores` is in the comparison's order (complete baskets first, cheapest first),
 * and that order decides which pins win when they would overlap.
 */
export default function BasketMap({ stores, myCoords, onCoords, visible, onlyComplete: onlyCompleteProp, onOnlyCompleteChange, onSelectStore, highlightId, onBoundsChange, onFailed, recenterKey }: {
  stores: BasketStoreTotal[];
  /** False while the list is shown: the map stays mounted but has no size */
  visible: boolean;
  myCoords: Coords | null;
  /** Shared with the list: show only branches that have the whole basket. Without these the map keeps its own switch. */
  onlyComplete?: boolean;
  onOnlyCompleteChange?: (on: boolean) => void;
  /** Told when the visitor picks (or closes) a branch on the map, so the list can scroll to it */
  onSelectStore?: (id: number | null) => void;
  /** The branch whose list card the pointer is over: its pin is drawn emphasised */
  highlightId?: number | null;
  /** The area the map shows now (after every move), so the list beside it can follow */
  onBoundsChange?: (b: { west: number; south: number; east: number; north: number }) => void;
  /** Told when the map cannot be drawn on this device (no WebGL), so the page can show its plain list instead */
  onFailed?: () => void;
  /** Changes whenever the page asks the map to go back to the area it opened on */
  recenterKey?: number;
  /** The visitor's position, when the map's own button found it */
  onCoords: (coords: Coords) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const pins = useRef(new Map<number, maplibregl.Marker>());
  const selectedRef = useRef<number | null>(null);
  const highlightRef = useRef<number | null>(null);
  const boundsRef = useRef(onBoundsChange);
  boundsRef.current = onBoundsChange;
  const failedRef = useRef(onFailed);
  failedRef.current = onFailed;
  // The list beside the map follows what the map shows, but only once the map has gone to its opening area:
  // before that it would show the whole country for a moment
  const fitted = useRef(false);
  highlightRef.current = highlightId ?? null;
  const [selected, setSelected] = useState<BasketStoreTotal | null>(null);
  const [failed, setFailed] = useState(false);
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  // Baskets that lack products look cheaper than they are, so by default only complete ones are drawn
  // (when there is at least one complete basket on the map; otherwise the partial ones are all there is).
  const [ownOnlyComplete, setOwnOnlyComplete] = useState(true);
  const onlyComplete = onlyCompleteProp ?? ownOnlyComplete;
  const setOnlyComplete = (on: boolean) => (onOnlyCompleteChange ?? setOwnOnlyComplete)(on);
  const located = useMemo(() => stores.filter(isMappable), [stores]);
  const partialCount = located.filter(s => s.items_missing > 0).length;
  const filterComplete = onlyComplete && partialCount > 0 && partialCount < located.length;
  const mapped = useMemo(() => filterComplete ? located.filter(s => s.items_missing === 0) : located, [located, filterComplete]);
  const hidden = stores.length - located.length;
  // Everything the draw function reads is kept in a ref so the map's own event handlers never go stale
  const data = useRef({ mapped, myCoords });
  data.current = { mapped, myCoords };

  function draw() {
    const map = mapRef.current;
    if (!map) return;
    const { mapped: all, myCoords: me } = data.current;
    const bounds = map.getBounds();
    const bestStore = pickBest(all, me, s => bounds.contains([s.store.longitude!, s.store.latitude!]));
    const best = bestStore?.store.id;
    const taken: { x: number; y: number }[] = [];
    const keep = new Set<number>();
    const place = (s: BasketStoreTotal, force: boolean) => {
      const p = map.project([s.store.longitude!, s.store.latitude!]);
      if (!force && taken.some(t => Math.abs(t.x - p.x) < PIN_W && Math.abs(t.y - p.y) < PIN_H)) return;
      taken.push({ x: p.x, y: p.y });
      keep.add(s.store.id);
    };
    const sel = all.find(s => s.store.id === selectedRef.current);
    if (sel) place(sel, true);
    if (bestStore && bounds.contains([bestStore.store.longitude!, bestStore.store.latitude!])) place(bestStore, true);
    for (const s of all) {
      if (keep.size >= MAX_PINS) break;
      if (keep.has(s.store.id) || !bounds.contains([s.store.longitude!, s.store.latitude!])) continue;
      place(s, false);
    }
    for (const [id, marker] of pins.current) {
      if (!keep.has(id)) { marker.remove(); pins.current.delete(id); }
    }
    for (const s of all) {
      if (!keep.has(s.store.id)) continue;
      let marker = pins.current.get(s.store.id);
      if (!marker) {
        // MapLibre moves the marker element with an inline transform, so the pill (which animates) is a child of it
        const wrap = document.createElement('div');
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.addEventListener('click', e => { e.stopPropagation(); selectStore(s); });
        wrap.appendChild(pill);
        marker = new maplibregl.Marker({ element: wrap, anchor: 'bottom' })
          .setLngLat([s.store.longitude!, s.store.latitude!]).addTo(map);
        pins.current.set(s.store.id, marker);
      }
      const el = marker.getElement();
      const pill = el.firstElementChild as HTMLButtonElement;
      const isBest = s.store.id === best && s.items_missing === 0;
      pill.className = `map-pin${isBest ? ' map-pin-best' : ''}${s.items_missing > 0 ? ' map-pin-partial' : ''}${s.store.id === selectedRef.current ? ' map-pin-selected' : ''}${s.store.id === highlightRef.current ? ' map-pin-hover' : ''}`;
      pill.textContent = priceText(s.total_price);
      pill.setAttribute('aria-label', `${s.store.chain.name}, ${money(s.total_price)}${s.items_missing > 0 ? `, חסרים ${s.items_missing} מוצרים` : ''}`);
      el.style.zIndex = s.store.id === selectedRef.current ? '3' : s.store.id === highlightRef.current ? '3' : isBest ? '2' : '1';
    }
  }

  function selectStore(s: BasketStoreTotal | null) {
    selectedRef.current = s ? s.store.id : null;
    setSelected(s);
    draw();
    onSelectStore?.(s ? s.store.id : null);
  }

  // Create the map once
  useEffect(() => {
    if (!box.current) return;
    setup();
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: box.current,
        style: mapStyle(window.location.origin),
        center: [34.85, 32.05], zoom: 9, minZoom: MIN_ZOOM, maxZoom: 16,
        maxBounds: ISRAEL_BOUNDS,
        attributionControl: { compact: true },
        dragRotate: false, pitchWithRotate: false, touchPitch: false,
        cooperativeGestures: false,
      });
    } catch {
      setFailed(true);          // no WebGL on this device
      failedRef.current?.();
      return;
    }
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    const reportBounds = () => {
      const b = map.getBounds();
      if (fitted.current) boundsRef.current?.({ west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() });
    };
    map.on('moveend', draw);
    map.on('moveend', reportBounds);
    map.on('load', reportBounds);
    map.on('click', () => selectStore(null));
    mapRef.current = map;
    const markers = pins.current;
    return () => {
      markers.clear();
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Goes to the opening area: around the visitor when known, otherwise where most of the branches are */
  function fitToStores() {
    const map = mapRef.current;
    if (!map) return;
    const all = data.current.mapped, me = data.current.myCoords;
    fitted.current = true;
    if (me && all.length > 0) {
      showAround(me, 0);                              // where the visitor is, with the branches around them
    } else if (all.length > 0) {
      // Not located: the area where most of the branches are, not the corner the few cheapest ones happen to be in
      const lats = all.map(s => s.store.latitude!).sort((a, b) => a - b);
      const lngs = all.map(s => s.store.longitude!).sort((a, b) => a - b);
      const at = (v: number[], q: number) => v[Math.min(v.length - 1, Math.floor(q * v.length))];
      const view = new maplibregl.LngLatBounds([at(lngs, 0.1), at(lats, 0.1)], [at(lngs, 0.9), at(lats, 0.9)]);
      map.fitBounds(view, { padding: 40, maxZoom: 12, duration: 0 });
    } else {
      draw();
      const b = map.getBounds();
      boundsRef.current?.({ west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() });
    }
  }

  // New results (a different set of located branches): go to the opening area
  useEffect(() => {
    if (!mapRef.current) return;
    selectedRef.current = null;
    setSelected(null);
    for (const m of pins.current.values()) m.remove();
    pins.current.clear();
    fitted.current = false;
    fitToStores();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [located]);

  // The "complete baskets only" switch: the pins change, the view stays where the visitor put it
  useEffect(() => {
    if (!mapRef.current || !fitted.current) return;
    for (const m of pins.current.values()) m.remove();
    pins.current.clear();
    if (selectedRef.current != null && !mapped.some(s => s.store.id === selectedRef.current)) {
      selectedRef.current = null;
      setSelected(null);
    }
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapped]);

  // The page asked to go back to the opening area
  const lastRecenter = useRef(recenterKey);
  useEffect(() => {
    if (recenterKey === lastRecenter.current) return;
    lastRecenter.current = recenterKey;
    fitToStores();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recenterKey]);

  /** Where the visitor is, and the branches around them: the map goes there. Stays in the browser, nothing is sent. */
  function showAround(me: Coords, duration = 700) {
    const map = mapRef.current;
    if (!map) return;
    shownFor.current = `${me.lat.toFixed(4)},${me.lng.toFixed(4)}`;
    const near = [...data.current.mapped]
      .sort((a, b) => distanceKm(me.lat, me.lng, a.store.latitude!, a.store.longitude!) - distanceKm(me.lat, me.lng, b.store.latitude!, b.store.longitude!))
      .slice(0, 6);
    const view = new maplibregl.LngLatBounds([me.lng, me.lat], [me.lng, me.lat]);
    near.forEach(s => view.extend([s.store.longitude!, s.store.latitude!]));
    map.fitBounds(view, { padding: { top: 70, bottom: 60, left: 50, right: 50 }, maxZoom: 14, duration });
  }

  /** `auto`: the map found the visitor by itself on opening; it stays quiet when that does not work. */
  function locateMe(auto = false) {
    setGeoError(null);
    if (myCoords && !locating) { showAround(myCoords); }
    if (!window.isSecureContext || !('geolocation' in navigator)) {
      if (!auto) setGeoError('המכשיר או הדפדפן לא מאפשרים לאתר מיקום בדף הזה.');
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      pos => {
        setLocating(false);
        const me = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        saveMyCoords(me);
        onCoords(me);
        showAround(me);
      },
      err => {
        setLocating(false);
        if (auto) return;
        setGeoError(err.code === err.PERMISSION_DENIED
          ? 'הגישה למיקום חסומה. אפשר לאפשר אותה בהגדרות הדפדפן.'
          : 'לא הצלחנו לאתר אותך. נסו שוב.');
      },
      { timeout: 10000, maximumAge: 5 * 60 * 1000 },
    );
  }

  // Shown again after the list: the map was laid out while hidden
  useEffect(() => { draw(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [highlightId]);

  const autoLocated = useRef(false);
  useEffect(() => {
    if (!visible) return;
    mapRef.current?.resize();
    // The first time the map is seen without a known position, find the visitor: nobody should have to look for themselves
    if (!myCoords && !autoLocated.current) {
      autoLocated.current = true;
      locateMe(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  // The visitor's own position
  const me = useRef<maplibregl.Marker | null>(null);
  const shownFor = useRef('');
  useEffect(() => {
    const map = mapRef.current;
    me.current?.remove(); me.current = null;
    if (!map || !myCoords) return;
    const el = document.createElement('div');
    el.className = 'map-me';
    el.setAttribute('aria-label', 'המיקום שלך');
    me.current = new maplibregl.Marker({ element: el }).setLngLat([myCoords.lng, myCoords.lat]).addTo(map);
    draw();                       // the green pin follows the visitor's position
    // A position found elsewhere on the page (not by this map's own button): show where they are
    const key = `${myCoords.lat.toFixed(4)},${myCoords.lng.toFixed(4)}`;
    if (shownFor.current !== key) { shownFor.current = key; if (fitted.current && data.current.mapped.length > 0) showAround(myCoords); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [myCoords]);

  const km = selected && myCoords && selected.store.latitude != null
    ? distanceKm(myCoords.lat, myCoords.lng, selected.store.latitude, selected.store.longitude!)
    : null;
  const text = selected && {
    chain: selected.store.chain.name, name: selected.store.name, address: selected.store.address, city: selected.store.city,
  };

  if (failed) {
    return <div className="map-note">המפה לא זמינה במכשיר הזה. הרשימה מציגה את אותן תוצאות.</div>;
  }

  return (
    <div className="basket-map">
      <div ref={box} className="basket-map-canvas" />

      {!selected && (
        <button className="map-locate" onClick={() => locateMe()} disabled={locating}>
          <Locate size={15} strokeWidth={2} />
          {locating ? 'מאתר...' : myCoords ? 'המיקום שלי' : 'מה קרוב אליי'}
        </button>
      )}
      {geoError && !selected && <div className="map-geo-error" role="status">{geoError}</div>}

      {mapped.length === 0 && (
        <div className="map-empty">אין לנו עדיין מיקום מדויק לסניפים האלה. הרשימה מציגה את כולם.</div>
      )}

      {selected && text && (
        <div className="map-card" role="dialog" aria-label={`${selected.store.chain.name}, פרטי הסניף`}>
          <button className="map-card-close" onClick={() => selectStore(null)} aria-label="סגירה"><X size={16} strokeWidth={2.2} /></button>
          <div className="map-card-head">
            <ChainLogo name={selected.store.chain.name} size={40} />
            <div className="map-card-info">
              <div className="map-card-name">{selected.store.chain.name}</div>
              <div className="map-card-sub">{storeSubtitle(text) || selected.store.city}</div>
              {km != null && <div className="map-card-sub">{km.toFixed(1)} ק״מ ממך</div>}
            </div>
            <div className="map-card-price tabular">{money(selected.total_price)}</div>
          </div>
          {selected.items_missing > 0 && (
            <div className="map-card-warn">חסרים {selected.items_missing} מוצרים מהסל בסניף הזה</div>
          )}
          {!isOnlineStore(text) && (
            <div className="store-row-actions">
              <a href={wazeLink(text)} target="_blank" rel="noopener noreferrer"><Navigation size={12} strokeWidth={2} />Waze</a>
              <a href={googleMapsLink(text)} target="_blank" rel="noopener noreferrer"><MapPin size={12} strokeWidth={2} />Maps</a>
            </div>
          )}
        </div>
      )}

      <div className="map-legend">
        <span className="map-legend-dot" />
        {myCoords ? `הירוק: הכי זול בקרבתך (עד ${NEAR_KM} ק״מ) באזור שמוצג` : 'הירוק: הכי זול באזור שמוצג במפה'}
        {partialCount > 0 && !filterComplete && ' · מסגרת אדומה: חסרים מוצרים'}
      </div>

      {partialCount > 0 && partialCount < located.length && (
        <button className={`map-filter${filterComplete ? ' active' : ''}`} aria-pressed={filterComplete} onClick={() => setOnlyComplete(!filterComplete)}>
          {filterComplete ? `רק סניפים עם כל המוצרים · מוסתרים ${partialCount}` : 'הציגו גם סניפים שחסרים בהם מוצרים'}
        </button>
      )}

      {hidden > 0 && mapped.length > 0 && (
        <div className="map-hidden-note">{hidden} סניפים בלי מיקום מדויק מופיעים רק ברשימה</div>
      )}
    </div>
  );
}
