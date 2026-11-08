# Map tiles

The basket map (`frontend/src/components/BasketMap.tsx`) reads one PMTiles file, `il.pmtiles`, served by nginx at
`/tiles/il.pmtiles`. Nothing is fetched from a third-party map service. The file is not in git (about 87 MB);
nginx mounts this folder read-only at `/srv/tiles`.

## Make or refresh the file (every few months is plenty)

Needs the `pmtiles` CLI from <https://github.com/protomaps/go-pmtiles/releases>.

```bash
# newest daily build of the OpenStreetMap-based Protomaps basemap
latest=$(curl -s https://build-metadata.protomaps.dev/builds.json | python3 -c "import json,sys; print(json.load(sys.stdin)[-1]['key'])")
# only Israel's pieces are downloaded (HTTP Range), up to zoom 14: about 87 MB
pmtiles extract "https://build.protomaps.com/$latest" il.pmtiles --bbox=34.2,29.4,35.9,33.4 --maxzoom=14
```

## Put it on the server

```bash
scp il.pmtiles <server>:<project folder>/deploy/tiles/il.pmtiles
```

Replace the file in one step (copy to `il.pmtiles.new` on the server, then `mv il.pmtiles.new il.pmtiles`) so a visitor never reads a half-written file. No restart is needed: nginx reads the file on every request and browsers revalidate it. For local development copy it to
`frontend/public/tiles/il.pmtiles` (also not in git).

## Credit

The map shows "© OpenStreetMap" (required by the data licence, ODbL). Label fonts are Noto Sans (SIL OFL), in
`frontend/public/map/fonts`, from <https://github.com/protomaps/basemaps-assets>.
