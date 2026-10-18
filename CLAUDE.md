# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the API server
uvicorn main:app --reload

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Ingestion worker (scrape -> parse -> delete), the production entry point
python -m app.worker                           # run forever, cycles at RUN_AT (06:00 and 18:00)
python -m app.worker --once                    # one cycle, then exit
python -m app.worker --once --chains SHUFERSAL --no-scrape   # only load what is in dumps/

# Individual pieces
python -m app.scraper.mass_scraper             # multi-chain download (il-supermarket-scraper)
python -m app.scraper.run_chain SHUFERSAL      # one chain, own process
python -m app.scraper.preflight                # can THIS machine reach every chain?
python -m app.parser.mass_parser [CHAIN ...]   # load downloaded files into PostgreSQL

# Production (single VPS): api + worker + db + backup + nginx
docker compose up -d --build

# Tests (creates and drops a throw-away database named sm_pytest)
pytest
```

Environment: requires a `.env` file with `DATABASE_URL` (async PostgreSQL URL, e.g. `postgresql+asyncpg://...`). All other knobs live in `app/settings.py` (see `.env.example`). `pytest` refuses to run unless the test database name contains `test`.

## Architecture

**Data pipeline:** Scraper → `dumps/<Chain>/*.xml` → Parser → PostgreSQL → FastAPI (the XML is deleted after it is committed in production)

### Scraper layer (`app/scraper/`)
- `mass_scraper.py`: `scrape_chain()` downloads one chain's store and FULL price files via `il-supermarket-scraper` (delta files are not used: a daily full file is self-correcting), plus FULL promo files when `SCRAPE_PROMOS` is on for that chain (`PROMO_CHAINS` limits it, see `settings.promos_enabled_for`); `run_mass_scraper()` loops chains and keeps going when one fails. 
- `run_chain.py`: one chain in its own process. The worker launches it per chain so a hang can be killed on a timeout.
- `preflight.py`: downloads one small file per chain to verify a machine can reach them (use it on every new server).
- **Download dedup is the library's own status database** (`dumps/status/<chain>.json`, by file name), *not* "file exists on disk". That is what makes deleting loaded files safe. Keep `dumps/status` on persistent storage.
- 12 chains (`BLOCKED_FROM_ABROAD`) only answer Israeli IPs.

### Parser layer (`app/parser/`)
- `mass_parser.py`: `parse_chain(name)` loads one chain's files. Per file: check the XML is well-formed (the chain parsers silently "repair" truncated files in place), load in one transaction together with its `ingested_files` ledger row, delete the file after commit. Of the full price files only the newest per store is loaded; older ones are recorded as `superseded` and skipped. Files are applied oldest first, stores before prices. A file that fails 3 times is moved to `dumps/_quarantine/`.
- `price_loader.py`: set-based product/price load in chunks of 500 (a few queries per chunk, not per row).
- `ledger.py`: the `ingested_files` ledger and file housekeeping. A file is loaded when its ledger row says `done`, never because of what is on disk.
- `promo_loader.py` and the `PromoFull` path in `mass_parser.py`: loads promo files (only when `promos_enabled_for(chain)`), after the price files, newest per store, one transaction with the ledger row (`file_type` `promo_full`). `promotions` is a per-store snapshot: each newer full file replaces that store's rows (the "never delete" rule is for `prices`). `normalize_promotion` keeps only promotions for everybody (no club/coupon audience), reward codes 1/2/3/10, still running, with at most 100 items; reward 6's `DiscountedPrice` is the gift's price, so those are dropped. Phase A only shows the chain's own text: **no price is computed from a promotion**.
- `universal_parser.py`: field-name helpers, chain and store upserts.
- **Price history strategy**: each price row has `is_current`; the database allows exactly one current row per `(store, product)` (partial unique index). On a price change the old row is set `is_current=False` and a new row is inserted. A file with an older `price_updated_at` than the stored one is ignored. A full file closes products it no longer lists, unless it lists under half of what we hold (truncated-file guard).

### Product pictures (`app/images.py`, `app/pipeline/images.py`)
Two sources, asked in the worker after each cycle: Shufersal's catalogue (`fill_images`, `image_checked_at`), then Open Food Facts for what Shufersal did not carry (`fill_images_off`, `off_checked_at`, `OFF_IMAGE_FILL_MINUTES`). OFF is asked two requests at a time, paced (about 20 a minute: four at a time, ~60 a minute, was answered with 429 although their stated limit is ~100), products of the promotions section first, real GTINs only. A failed lookup is never recorded as "no picture". Pictures are served only from allowed hosts (`is_allowed_image_url`, and the CSP in `nginx/nginx.conf`); OFF's are CC BY-SA, credited on the About page.

**A picture must be of this product.** Shufersal's search is fuzzy, so a result counts only if its own code is the barcode (`code_matches_barcode`: equal, the private-label tail 7290000+code, or UPC/EAN zero-padding); failing that, by name only when `names_match`: the first meaningful word of our name (the category) is in theirs, and so is every other word (a name of 5+ words may miss one). Never match by loose word overlap: a corn once got a mayonnaise's picture. `python -m app.pipeline.images audit [--dry-run]` re-checks the pictures whose code is not the barcode (replace / clear / leave on failure), with a known-good canary before every page.

### Database (`app/db/`)
Tables: `chains` → `stores` → `prices` ← `products`, and `promotions`; plus the operational `ingested_files` (file ledger) and `ingest_runs` (cycle/chain/phase log).
- `Chain`: one row per supermarket company. Shufersal=`7290027600007`, Victory=`7290696200003`.
- `Store`: one branch. Identified by `(chain_id, store_id)` composite unique index — store IDs are chain-scoped (same "001" exists in multiple chains).
- `Product`: keyed by barcode (GTIN). First-seen name wins; later chains don't overwrite it.
- `Price`: uses `Numeric(10, 2)` — never `Float` for money.
- `Promotion`: one row per product of a promotion in a store (unique on `promotion_id, store_id, product_id`), loaded from promo XML files; empty until `SCRAPE_PROMOS` is on.
- `promo_deals` (materialized view, refreshed by the worker after `product_store_counts`, which it joins): one row per brand and promotion terms for the promotions section, with the stores and products it covers and `saving_pct` against the cheapest shelf price of its products.

Requires the `pg_trgm` PostgreSQL extension (enabled in the initial migration) for the GIN trigram index on `products.name`, which powers Hebrew text search with `ILIKE`.

### API layer (`app/api/`)
Three endpoints under `/api/v1`:
- `GET /products/search?q=` — barcode (exact) or Hebrew name (`ILIKE %q%`)
- `GET /products/{barcode}/compare` — prices across all stores, sorted cheapest first; each row carries `promotions` (up to 3 running now, soonest end first, the chain's wording only)
- `POST /basket/compare` — total cost of a list of `{barcode, quantity}` items per store, sorted cheapest first. A line is priced with the best single-product "N for X" promotion (`promotions.basket_eligible`, reward codes 1/10) only for stores whose `last_promo_at` is within 7 days; `unit_price` is the shelf price, `line_total` is promotion-adjusted, each store reports `savings` and `promotions_known`; a promotion that covers several basket products is returned as a store-level entry in `promo_adjustments` and subtracted from `total_price`
- `GET /deals` — promotions across brands (home strip and `/promotions` page): filters `chain`, `city`, `kind`, `sort`, `diverse`; `GET /deals/{deal_id}/products` lists a group promotion's products

All DB access is async (`AsyncSession` via `asyncpg`). FastAPI dependency `get_db` provides a session per request.

### Ingestion worker (`app/worker.py`, `app/pipeline/`)
Two cycles a day (`RUN_AT`, default 06:00 and 18:00 Israel time; a failed or partial cycle is retried up to twice, 2 hours apart). The evening cycle downloads only files published since the morning one. One cycle = for every chain: scrape (subprocess, timeout, retries) then parse. Chains are isolated: a failure is recorded in `ingest_runs` and never stops the others. A Postgres advisory lock allows one cycle at a time across processes and hosts. `GET /health/data` is 503 when the last successful cycle is older than `MAX_DATA_AGE_HOURS`. Celery/Redis are no longer used; there are no `/tasks` API endpoints.

## Rules

**Money is always `Decimal`/`Numeric(10, 2)`.** Never use `float` for prices. `6.50 + 3.30` in float gives `9.799999...`. Use `Decimal` in Python and `Numeric(10, 2)` in SQLAlchemy columns.

**All DB access must be async.** Use `AsyncSession`, `await session.execute(...)`, and `async with AsyncSessionLocal()`. Never import or use the synchronous SQLAlchemy session.

**XML field names must be lowercased before access.** `parse_xml_items` normalizes all tags to lowercase. Always access parsed item dicts with lowercase keys (e.g. `item.get("itemcode")`, not `item.get("ItemCode")`). When adding support for a new chain, check what field names it uses and add them to the fallback chains (e.g. `item.get("manufacturername") or item.get("manufacturename")`).

**Store IDs are chain-scoped.** The same `store_id` string (e.g. `"001"`) exists in multiple chains. Always look up stores by `(chain_id, store_id)` together, never by `store_id` alone.

**Product names: first-seen wins.** The product insert is `ON CONFLICT (barcode) DO NOTHING`, so an existing product's name is never updated. This is intentional — don't change it to overwrite names on re-parse.

**Price history via `is_current` flag.** Never delete price rows (the opt-in `HISTORY_RETENTION_DAYS` is the only exception and is off by default). When a price changes, set the old row's `is_current = False` and insert a new row, closing before inserting. When a price is unchanged, **write nothing** to its row: a complete (`PriceFull`) file sets `stores.last_full_at` once for the store, which confirms every price the file still lists (rewriting ~11 million unchanged rows a day kept the database saturated and bloated the table). The API reports `scraped_at` as the newer of the row's own stamp and the store's `last_full_at`.

**Parser works in chunks of 500 items.** Each chunk is a handful of set-based statements (`PARSE_BATCH_SIZE`). Never go back to one query per row, and keep one transaction per file (data + ledger row), never one per item.

**Schema changes need a migration.** Any schema change (new column, new index) requires a new Alembic migration: `python -m alembic revision --autogenerate -m "description"`. The `pg_trgm` extension is already enabled — don't re-create it. The production API connects as the read-only `api_ro` role, so a new table is readable automatically (default privileges) but any new API *write* needs an explicit grant in a migration.

**Files are deduplicated by name, in two places.** The scraper skips names its status database has verified (`dumps/status`), and the parser skips names whose `ingested_files` row is `done`. Don't change either: re-downloading wastes bandwidth and re-parsing wastes DB writes. Never decide "already loaded" from the presence of a file on disk.

**A deal is shown only if it is clearly cheaper than the market.** `promo_deals` holds running, `basket_eligible` promotions of stores whose promotion data is at most 7 days old, on products with a real barcode (7+ characters) and a trusted price (the text confirmed the total for N, or it is a one-unit price), with `saving_pct` against the cheapest shelf price of the deal's products (`product_store_counts.min_price`, at least 0.50). `vs_market` says whether another brand also sells every product (otherwise the reference is the brand's own shelf and the card says so); deals compared with the market rank first, and every order ends with `deal_id` so paging is stable. `/deals` returns these rules in `rules` (a test pins the 0.50 to the view) and shows 10% to 60% savings only (`MIN_DEAL_SAVING`, `MAX_DEAL_SAVING` in `app/api/routes.py`) and re-checks the end date at query time. The brand is split like `display_chain_name` (a test pins the SQL).

**API responses sort cheapest first.** `/products/{barcode}/compare` and `/basket/compare` both return results ordered by price ascending. Maintain this contract when modifying these endpoints.

**A promotion changes a basket total only when it is `basket_eligible`.** One product, or a group of products whose price the promotion text confirms ("N ב-price"); reward 1 or 10; one `<Group>`; not weighted/gift/redemption-limited; running now; the store's promotion data fresh (`stores.last_promo_at`, 7 days). `app/basket_promos.price_store` applies them: a product belongs to at most one promotion, the largest total saving goes first, a group's sets take the cheapest units first, a set that saves nothing is never taken. Club, coupon, reward-3 and multi-`<Group>` promotions stay display-only.

**Never mark a file loaded without its data.** The ledger row is written in the same transaction as the prices, and the XML is deleted only after commit. Don't move either step outside the transaction.

**Check XML integrity before parsing.** `il_supermarket_parsers` repairs a truncated file in place and then yields only the items before the cut. `assert_well_formed` must run before the parser reads a file.
