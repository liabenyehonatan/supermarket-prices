# Production Hardening & Feature Completion — Design Spec

**Date:** 2026-05-12  
**Scope:** Full upgrade of the Israeli supermarket price comparison app to premium production quality  
**Phases:** 4 (Critical → High → Reliability → Polish)

---

## Context

The app is a Next.js + FastAPI + PostgreSQL + Celery system that scrapes price XML files from 34 Israeli supermarket chains, parses them into a DB, and exposes a basket-comparison UI. The core pipeline works. This spec covers everything needed to take it from functional prototype to public production.

---

## Phase 1 — Critical Fixes

### 1.1 API Key Auth on Task Endpoints

**Problem:** `POST /api/v1/tasks/scrape|parse|scrape-and-parse` are fully public. Anyone can trigger pipeline runs.

**Solution:**
- Add `ADMIN_API_KEY` to `.env` and `.env.example`
- Create `app/api/auth.py` with a `verify_api_key` FastAPI dependency that reads the `X-Api-Key` header and raises `HTTP 401` on mismatch
- Apply the dependency to all `/api/v1/tasks/*` routes in `main.py`
- Apply the same dependency to the new `GET /api/v1/admin/chain-stats` endpoint (Phase 4)

### 1.2 CORS

**Problem:** `allow_origins=["*"]` is hardcoded in `main.py`.

**Solution:**
- Read `FRONTEND_URL` from env (e.g. `https://machirista.co.il`)
- Pass `[FRONTEND_URL]` as `allow_origins` when the var is set; fall back to `["*"]` when unset (local dev only)
- Add `FRONTEND_URL` to `.env.example`

### 1.3 nginx.conf

**Problem:** `docker-compose.yml` mounts `nginx/nginx.conf` but the file doesn't exist — deployment is broken.

**Solution:** Create `nginx/nginx.conf` with:
- `/` → `frontend:3000` (proxy_pass)
- `/api/` and `/docs` and `/openapi.json` → `api:8000`
- `gzip on` for text/html/json/css/js
- Security headers: `X-Frame-Options SAMEORIGIN`, `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`
- Client-side cache headers for static assets (`/_next/static/`)

### 1.4 Basket Ranking Fix

**Problem:** Stores with partial basket coverage rank above complete-basket stores based on lower total.

**Solution:**
- Add `coverage_pct: float` to `BasketStoreTotal` schema (= `items_found / total_items_requested`)
- Change sort in `compare_basket` to `(coverage_pct DESC, total_price ASC)`
- Frontend `BasketResults.tsx`: insert a visual divider between stores where `coverage_pct == 1.0` and those below. Partial stores get an amber badge showing "חסרים X פריטים".

### 1.5 Transfer Basket

**Problem:** The primary CTA in `BasketResults.tsx` calls `alert()`.

**Solution:**
- Create `app/utils/transfer.py` with `get_transfer_url(chain, store, barcodes) -> str | None`:
  - If `store.delivery_url` is set → return it directly
  - Elif `chain.online_store_url_template` is set → substitute `{barcode}` for the first barcode (or comma-joined list depending on chain format)
  - Elif `chain.website_url` → return that
  - Else → return `None`
- Expose transfer URL in the `BasketStoreTotal` response as `transfer_url: str | None`
- `BasketResults.tsx`: replace `alert()` with `window.open(transfer_url, "_blank")`. Disable button (greyed, tooltip "אין חנות מקוונת") when `transfer_url` is null.

### 1.6 Remove Dead Vite Code

**Files to delete from `frontend/src/`:**
- `main.tsx`
- `App.tsx`
- `pages/` (entire directory)
- `styles/global.css`
- `vite-env.d.ts`
- `api/client.ts`

These are leftovers from the original Vite setup and are completely unreachable in the Next.js App Router.

---

## Phase 2 — Core Feature Gaps

### 2.1 Promotions API + UI

**New endpoints:**
- `GET /api/v1/products/{barcode}/promotions` → `List[PromotionResponse]`  
  Returns active promotions (`is_active=True`, `end_date > now OR end_date IS NULL`) for the product, with store and chain info.
- Inline in `GET /api/v1/products/{barcode}/compare`: add `promotion: PromotionResponse | None` to each `PriceAtStore` entry (the best active promotion for that store, if any).

**Schema `PromotionResponse`:**
```
promotion_id, description, discounted_price, min_qty, start_date, end_date, store_name, chain_name
```

**UI:**
- Product compare page: each price row shows a green pill with promotion description when `promotion` is non-null
- Basket results: cheapest store card shows a "🏷 מבצע זמין" indicator when any basket item has an active promotion there

### 2.2 Price History + Sparkline

**New endpoint:** `GET /api/v1/products/{barcode}/history?days=30`

Query: all price rows (both `is_current=True` and `False`) for this barcode within the last N days. Group by `(chain_name, date(price_updated_at))`, take the min price per group. Return as:
```json
[{"chain_name": "שופרסל", "date": "2026-05-01", "price": 12.90}, ...]
```

**Frontend:**
- Wire `PriceSparkline.tsx` into the product page, below the cheapest/most-expensive/difference summary grid
- One line per chain, limited to the top 5 chains by number of historical price rows for this barcode (i.e. the chains that have tracked this product longest), 30-day window
- Tooltip on hover: chain name + date + price

### 2.3 Data Freshness Indicators

**New endpoint:** `GET /api/v1/stats`
```json
{
  "products_count": 120000,
  "chains_count": 34,
  "stores_count": 3200,
  "prices_count": 4500000,
  "last_updated": "2026-05-12T06:00:00"
}
```
`last_updated` = `MAX(scraped_at)` from the prices table.

**Price rows:** Add `price_updated_at` formatted as relative time ("עודכן לפני שעתיים" / "updated 2h ago") to every price entry in:
- `ProductPage` price list
- `BasketResults` store cards

**StatsBar:** Convert to a client component, fetch `/api/v1/stats` on mount, SWR cache 1 hour. Skeleton placeholders while loading. Falls back gracefully if API is slow.

### 2.4 Fuzzy Hebrew Search

**Change in `routes.py` `search_products`:**

Replace single `ILIKE` query with a union:
1. `WHERE name ILIKE '%q%'` — exact substring hits, returned first
2. `WHERE word_similarity(q, name) > 0.25 AND name NOT ILIKE '%q%'` — fuzzy hits, returned after, ordered by `word_similarity DESC`

Combined with `LIMIT`. Uses the existing `ix_products_name_trgm` GIN index — no migration needed. Add `pg_trgm` function import to the query.

### 2.5 Geocoder in Pipeline

**New Celery task:** `geocode_new` in `app/tasks.py`
- Calls `geocode_all_stores(only_missing=True)` — add `only_missing` param to the geocoder
- Runs automatically after `parse_all` completes (chain the tasks)
- Also callable via `POST /api/v1/tasks/geocode` (API-key protected)
- Rate-limited to Nominatim's 1 req/sec (already implemented in geocoder)

**Beat schedule:** Add `geocode_new` to run nightly after the 2 AM full scrape.

### 2.6 "Near Me" Location Filter

**Backend changes:**
- Add optional query params to `POST /api/v1/basket/compare`: `lat: float | None`, `lng: float | None`, `radius_km: float | None` (default 20)
- When lat/lng provided: after loading all store prices, filter `store_objects` to only stores within radius using the Haversine formula (pure Python, no PostGIS required — store count is small enough)
- Same filter added to `GET /api/v1/products/{barcode}/compare`

**Frontend:**
- "סנן לפי מיקום" / "Near me" toggle button in `BasketBuilder` and on the product compare page
- On click: `navigator.geolocation.getCurrentPosition` → store coords in component state → re-run compare with coords
- If user denies geolocation: show toast "לא ניתן לגשת למיקום" and keep showing all stores
- Show "מוצגים X סניפים בטווח של 20 ק״מ" label when filter is active

---

## Phase 3 — Infrastructure Reliability

### 3.1 Fix `_run_async`

**In `app/tasks.py`:** Delete the `_run_async` helper entirely. Replace all call sites with `asyncio.run(coro)`. Each Celery task runs in its own thread with no existing event loop, so `asyncio.run()` is correct and simple.

### 3.2 Split Celery Beat + Worker

**In `docker-compose.yml`:**
- Rename existing `celery` service to `celery-worker`, command: `celery -A app.celery_app worker --loglevel=info`
- Add new `celery-beat` service, command: `celery -A app.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule`
- Both share the same `dumps` volume and env vars
- `celery-beat` depends on `redis` health check only (doesn't need DB directly)

### 3.3 Real Health Check

**Extend `GET /health` in `main.py`:**
```python
async def health(db: AsyncSession = Depends(get_db)):
    db_ok = redis_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except: pass
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except: pass
    status = "ok" if (db_ok and redis_ok) else "degraded"
    return JSONResponse(
        {"status": status, "db": db_ok, "redis": redis_ok},
        status_code=200 if status == "ok" else 503
    )
```
`redis` package is already a transitive dependency of `celery[redis]` — no new dependency needed. Read `REDIS_URL` from the same env var used by Celery.

### 3.4 Unblock Israeli-IP Chains

**Code changes:**
- Add `SKIP_BLOCKED_CHAINS` env var (default `"true"` for local dev, `"false"` on VPS)
- In `celery_app.py` Beat schedule: read `SKIP_BLOCKED_CHAINS` from env instead of hardcoding `skip_blocked=True`
- Add `SKIP_BLOCKED_CHAINS=false` to the VPS `.env` example

**Ops doc:** Create `docs/deployment.md` covering:
- Required: Israeli datacenter VPS (Hetzner Ashkelon / DigitalOcean IL / AWS il-central-1)
- Open outbound FTP port 21 (some hosts block it)
- `docker compose up -d` steps
- Setting `SKIP_BLOCKED_CHAINS=false`

### 3.5 Error Monitoring (Sentry)

- Add `sentry-sdk[fastapi,celery]` to `requirements.txt`
- Add `SENTRY_DSN` to `.env.example` (empty = disabled)
- Init in `main.py` (FastAPI integration) and `celery_app.py` (Celery integration)
- In `mass_parser.py`: change silent `logger.debug(f"Row error: {e}")` to `sentry_sdk.capture_exception(e)` when error rate exceeds 1% of batch (avoids flooding Sentry on a broken XML file)

---

## Phase 4 — Polish & Growth

### 4.1 Shareable Basket URL

**Client-side only — no backend needed.**

In `basket-store.ts`:
- Add `toShareUrl(): string` — encodes `items[]` as `btoa(JSON.stringify(items))`, returns `window.location.origin + /he/?b=<encoded>`
- Add `loadFromUrl(b: string)` — decodes and hydrates the basket, called on mount in `BasketBuilder` if `?b=` param is present

In `BasketBuilder.tsx`:
- When basket has ≥1 item and results exist: show a "שתף סל" / "Share basket" button that calls `navigator.clipboard.writeText(toShareUrl())` and shows a "הועתק!" toast for 2 seconds

### 4.2 Category Browsing

**New endpoint:** `GET /api/v1/categories`
```json
[{"category": "מוצרי חלב", "count": 4200}, ...]
```
Returns distinct non-null categories ordered by product count desc.

**New search param:** `GET /api/v1/products/search?q=...&category=מוצרי חלב`

**Frontend `SearchPage`:**
- Horizontal scrollable chip row above results: "הכל" + one chip per top-10 category
- Active chip highlighted in brand color
- Selecting a chip triggers a search with `category` param (can combine with text query)

### 4.3 Admin Dashboard

**New endpoint:** `GET /api/v1/admin/chain-stats` (API-key protected)
```json
[{
  "chain_name": "שופרסל",
  "last_scraped": "2026-05-12T06:00:00",
  "file_count": 847,
  "products_parsed": 28000,
  "stores_total": 280,
  "stores_geocoded": 271,
  "geocoding_pct": 96.8
}, ...]
```

**New Next.js page:** `/admin`
- Password gate: env var `ADMIN_PASSWORD`, stored in `sessionStorage` on login, checked on every render
- Table of all chains with the above stats
- "Trigger pipeline" buttons per chain: calls `/api/v1/tasks/scrape-and-parse` with the chain name and the `X-Api-Key` header (key stored in env as `NEXT_PUBLIC_ADMIN_API_KEY` — acceptable since admin page is password-gated)
- Live task status polling: after triggering, polls `/api/v1/tasks/{id}` every 3 seconds, shows progress badge

### 4.4 Basket LocalStorage Expiry

**In `basket-store.ts`:**
- Add `savedAt: number` (Unix ms timestamp) to the persisted state
- On store initialization: if `savedAt` is older than 7 days → reset basket to empty, clear storage
- Update `savedAt` on every write

### 4.5 StatsBar Live Data

Covered by Phase 2.3 (`GET /api/v1/stats` endpoint + StatsBar client component rewrite).

---

## New Files Summary

| File | Purpose |
|---|---|
| `app/api/auth.py` | `verify_api_key` dependency |
| `app/utils/transfer.py` | `get_transfer_url()` helper |
| `nginx/nginx.conf` | Reverse proxy config |
| `docs/deployment.md` | VPS deployment guide |
| `docs/superpowers/specs/2026-05-12-production-hardening-design.md` | This file |

## Modified Files Summary

| File | Change |
|---|---|
| `main.py` | CORS, health check, auth on task routes |
| `app/api/routes.py` | Promotions, history, stats, categories, location filter, fuzzy search, chain-stats |
| `app/api/schemas.py` | New response types: PromotionResponse, StatsResponse, etc. |
| `app/tasks.py` | `_run_async` removed, `geocode_new` task added |
| `app/celery_app.py` | `SKIP_BLOCKED_CHAINS` env var, beat schedule updated |
| `app/parser/mass_parser.py` | Chain geocode call after store parse |
| `app/geocoder.py` | `only_missing` param |
| `docker-compose.yml` | Beat/worker split |
| `.env.example` | New vars: `ADMIN_API_KEY`, `FRONTEND_URL`, `SENTRY_DSN`, `SKIP_BLOCKED_CHAINS`, `ADMIN_PASSWORD` |
| `frontend/src/lib/api.ts` | New fetch functions for history, promotions, stats, categories |
| `frontend/src/lib/basket-store.ts` | `savedAt` expiry, `toShareUrl`, `loadFromUrl` |
| `frontend/src/components/basket/BasketResults.tsx` | Real transfer URL, coverage divider, share button |
| `frontend/src/components/basket/BasketBuilder.tsx` | Near-me toggle, URL param hydration |
| `frontend/src/components/layout/StatsBar.tsx` | Live data fetch |
| `frontend/src/app/[locale]/product/[barcode]/page.tsx` | Sparkline, promotions, freshness |
| `frontend/src/app/[locale]/search/page.tsx` | Category chips |
| `frontend/src/app/[locale]/admin/page.tsx` | New admin dashboard |

## Deleted Files

`frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/`, `frontend/src/styles/global.css`, `frontend/src/vite-env.d.ts`, `frontend/src/api/client.ts`

---

## Environment Variables (complete list of new vars)

| Var | Default | Purpose |
|---|---|---|
| `ADMIN_API_KEY` | — | Protects task + admin endpoints |
| `FRONTEND_URL` | unset (dev) | CORS allowlist |
| `SENTRY_DSN` | unset | Error monitoring (disabled if empty) |
| `SKIP_BLOCKED_CHAINS` | `true` | Set `false` on Israeli VPS |
| `ADMIN_PASSWORD` | — | Admin dashboard gate |
| `NEXT_PUBLIC_ADMIN_API_KEY` | — | Frontend calls to admin endpoints |

---

## Implementation Order

Phases are designed to be implemented in order — each phase's fixes make the next phase safer to build and deploy:

1. **Phase 1** — unblock deployment (nginx), secure the API, fix the basket bug users will hit immediately
2. **Phase 2** — add the features users will expect from a production product
3. **Phase 3** — make the infrastructure reliable enough for 24/7 operation
4. **Phase 4** — growth and ops polish

Within each phase, items are independent and can be parallelized.
