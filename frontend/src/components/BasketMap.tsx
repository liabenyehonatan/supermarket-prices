import { useEffect, useMemo, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import { Protocol } from 'pmtiles';
import 'maplibre-gl/dist/maplibre-gl.css';
import rtlTextPlugin from '@mapbox/mapbox-gl-rtl-text/mapbox-gl-rtl-text.min.js?url';
import { Locate, MapPin, Navigation, X } from 'lucide-react';
import { ChainLogo } from './ChainLogo';
import { ISRAEL_BOUNDS, mapStyle } from '../lib/mapStyle';
import { distanceKm } from '../lib/geo';
import { googleMapsLink, isOnlineStore, storeSubtitle, wazeLink } from '../lib/store';
import { money } from '../lib/safe';
import type { Coords } from '../lib/location';
import type { BasketStoreTotal } from '../types';

/** A branch we can put on the map: it has a position of its own, not just its town's centre. */
export function isMappable(s: BasketStoreTotal): boolean {
  const { latitude, longitude, geo_precision } = s.store;
  // Only a position found from the branch's own address counts: 'city' (the town's centre) and rows from before
  // precision was recorded would stack several branches on one spot and look exact when they are not.
  return latitude != null && longitude != null && geo_precision === 'address';
}

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
export default function BasketMap({ stores, myCoords, onLocate, visible }: {
  stores: BasketStoreTotal[];
  /** False while the list is shown: the map stays mounted but has no size */
  visible: boolean;
  myCoords: Coords | null;
  onLocate: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const pins = useRef(new Map<number, maplibregl.Marker>());
  const selectedRef = useRef<number | null>(null);
  const [selected, setSelected] = useState<BasketStoreTotal | null>(null);
  const [failed, setFailed] = useState(false);

  const mapped = useMemo(() => stores.filter(isMappable), [stores]);
  const hidden = stores.length - mapped.length;
  const cheapestId = stores[0]?.store.id;

  // Everything the draw function reads is kept in a ref so the map's own event handlers never go stale
  const data = useRef({ mapped, cheapestId });
  data.current = { mapped, cheapestId };

  function draw() {
    const map = mapRef.current;
    if (!map) return;
    const { mapped: all, cheapestId: best } = data.current;
    const bounds = map.getBounds();
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
      pill.className = `map-pin${isBest ? ' map-pin-best' : ''}${s.items_missing > 0 ? ' map-pin-partial' : ''}${s.store.id === selectedRef.current ? ' map-pin-selected' : ''}`;
      pill.textContent = priceText(s.total_price);
      pill.setAttribute('aria-label', `${s.store.chain.name}, ${money(s.total_price)}${s.items_missing > 0 ? `, חסרים ${s.items_missing} מוצרים` : ''}`);
      el.style.zIndex = s.store.id === selectedRef.current ? '3' : isBest ? '2' : '1';
    }
  }

  function selectStore(s: BasketStoreTotal | null) {
    selectedRef.current = s ? s.store.id : null;
    setSelected(s);
    draw();
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
        center: [34.85, 32.05], zoom: 9, maxZoom: 16,
        maxBounds: ISRAEL_BOUNDS,
        attributionControl: { compact: true },
        dragRotate: false, pitchWithRotate: false, touchPitch: false,
        cooperativeGestures: false,
      });
    } catch {
      setFailed(true);          // no WebGL on this device
      return;
    }
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('moveend', draw);
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

  // New results: show the cheapest branches (and the visitor, when known)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    selectedRef.current = null;
    setSelected(null);
    for (const m of pins.current.values()) m.remove();
    pins.current.clear();
    const view = new maplibregl.LngLatBounds();
    mapped.slice(0, 25).forEach(s => view.extend([s.store.longitude!, s.store.latitude!]));
    if (myCoords) view.extend([myCoords.lng, myCoords.lat]);
    if (!view.isEmpty()) map.fitBounds(view, { padding: { top: 60, bottom: 60, left: 50, right: 50 }, maxZoom: 14, duration: 0 });
    else draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapped]);

  // Shown again after the list: the map was laid out while hidden
  useEffect(() => {
    if (visible) mapRef.current?.resize();
  }, [visible]);

  // The visitor's own position
  const me = useRef<maplibregl.Marker | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    me.current?.remove(); me.current = null;
    if (!map || !myCoords) return;
    const el = document.createElement('div');
    el.className = 'map-me';
    el.setAttribute('aria-label', 'המיקום שלך');
    me.current = new maplibregl.Marker({ element: el }).setLngLat([myCoords.lng, myCoords.lat]).addTo(map);
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

      {!myCoords && !selected && (
        <button className="map-locate" onClick={onLocate}>
          <Locate size={15} strokeWidth={2} />
          מה קרוב אליי
        </button>
      )}

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

      {hidden > 0 && mapped.length > 0 && (
        <div className="map-hidden-note">{hidden} סניפים בלי מיקום מדויק מופיעים רק ברשימה</div>
      )}
    </div>
  );
}
