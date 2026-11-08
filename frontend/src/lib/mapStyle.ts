import { layers, namedFlavor } from '@protomaps/basemaps';
import type { StyleSpecification } from 'maplibre-gl';

// The map is served by us end to end: one Israel extract of the OpenStreetMap-based Protomaps basemap (a single
// PMTiles file, read with HTTP Range requests by nginx) and the label fonts. No third-party tile service, so no
// visitor address or area is sent anywhere and nothing can start refusing us. Refresh the file with
// deploy/tiles/README.md.
export const TILES_PATH = '/tiles/il.pmtiles';

const flavor = namedFlavor('light');

export function mapStyle(origin: string): StyleSpecification {
  return {
    version: 8,
    glyphs: `${origin}/map/fonts/{fontstack}/{range}.pbf`,
    sources: {
      protomaps: {
        type: 'vector',
        url: `pmtiles://${origin}${TILES_PATH}`,
        attribution: '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a>',
      },
    },
    // lang 'he': street and place names in Hebrew where OpenStreetMap has them, the local name otherwise.
    // The extract has no tiles for empty open sea, so the background is sea-coloured (land is drawn over it).
    layers: layers('protomaps', flavor, { lang: 'he' }).map(l =>
      l.id === 'background' ? { ...l, paint: { 'background-color': flavor.water } } : l) as StyleSpecification['layers'],
  };
}

/** Israel with a wide margin: the map cannot be dragged to where there are no tiles. The margin must stay larger
 *  than the map's size at its lowest zoom, otherwise there is nothing to drag (the map only zooms). */
export const ISRAEL_BOUNDS: [[number, number], [number, number]] = [[32.4, 27.6], [37.6, 35.0]];
export const MIN_ZOOM = 8;
