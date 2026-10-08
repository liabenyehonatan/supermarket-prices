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
python -m app.worker                           # run forever, every DELTA_EVERY_HOURS
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
- `mass_scraper.py`: `scrape_chain()` downloads one chain via `il-supermarket-scraper` (full files if the last full sync is older than 7 days, otherwise deltas); `run_mass_scraper()` loops chains and keeps going when one fails. The full-sync tracker is updated per chain, only after that chain succeeded.
- `run_chain.py`: one chain in its own process. The worker launches it per chain so a hang can be killed on a timeout.
- `preflight.py`: downloads one small file per chain to verify a machine can reach them (use it on every new server).
- **Download dedup is the library's own status database** (`dumps/status/<chain>.json`, by file name), *not* "file exists on disk". That is what makes deleting loaded files safe. Keep `dumps/status` on persistent storage.
- 12 chains (`BLOCKED_FROM_ABROAD`) only answer Israeli IPs.

### Parser layer (`app/parser/`)
- `mass_parser.py`: `parse_chain(name)` loads one chain's files. Per file: check the XML is well-formed (the chain parsers silently "repair" truncated files in place), load in one transaction together with its `ingested_files` ledger row, delete the file after commit. Files are applied oldest first, stores before prices. A file that fails 3 times is moved to `dumps/_quarantine/`.
- `price_loader.py`: set-based product/price load in chunks of 500 (a few queries per chunk, not per row).
- `ledger.py`: the `ingested_files` ledger and file housekeeping. A file is loaded when its ledger row says `done`, never because of what is on disk.
- `universal_parser.py`: field-name helpers, chain and store upserts.
- **Price history strategy**: each price row has `is_current`; the database allows exactly one current row per `(store, product)` (partial unique index). On a price change the old row is set `is_current=False` and a new row is inserted. A file with an older `price_updated_at` than the stored one is ignored. A full file closes products it no longer lists, unless it lists under half of what we hold (truncated-file guard).

**Legacy, not used by the worker:** `app/scraper/scraper_service.py` (Playwright, Shufersal), `app/scraper/victory_scraper.py` and `app/parser/parser_service.py` (GZ files, own per-row upserts). They predate the multi-chain pipeline and do not use the ledger or the bulk loader; don't run them against a production database.

### Database (`app/db/`)
Tables: `chains` → `stores` → `prices` ← `products`, and `promotions`; plus the operational `ingested_files` (file ledger) and `ingest_runs` (cycle/chain/phase log).
- `Chain`: one row per supermarket company. Shufersal=`7290027600007`, Victory=`7290696200003`.
- `Store`: one branch. Identified by `(chain_id, store_id)` composite unique index — store IDs are chain-scoped (same "001" exists in multiple chains).
- `Product`: keyed by barcode (GTIN). First-seen name wins; later chains don't overwrite it.
- `Price`: uses `Numeric(10, 2)` — never `Float` for money.
- `Promotion`: deal info from promo XML files.

Requires the `pg_trgm` PostgreSQL extension (enabled in the initial migration) for the GIN trigram index on `products.name`, which powers Hebrew text search with `ILIKE`.

### API layer (`app/api/`)
Three endpoints under `/api/v1`:
- `GET /products/search?q=` — barcode (exact) or Hebrew name (`ILIKE %q%`)
- `GET /products/{barcode}/compare` — prices across all stores, sorted cheapest first
- `POST /basket/compare` — total cost of a list of `{barcode, quantity}` items per store, sorted cheapest first

All DB access is async (`AsyncSession` via `asyncpg`). FastAPI dependency `get_db` provides a session per request.

### Ingestion worker (`app/worker.py`, `app/pipeline/`)
One cycle = for every chain: scrape (subprocess, timeout, retries) then parse. Chains are isolated: a failure is recorded in `ingest_runs` and never stops the others. A Postgres advisory lock allows one cycle at a time across processes and hosts. `GET /health/data` is 503 when the last successful cycle is older than `MAX_DATA_AGE_HOURS`. Celery/Redis are no longer used; there are no `/tasks` API endpoints.

## Rules

**Money is always `Decimal`/`Numeric(10, 2)`.** Never use `float` for prices. `6.50 + 3.30` in float gives `9.799999...`. Use `Decimal` in Python and `Numeric(10, 2)` in SQLAlchemy columns.

**All DB access must be async.** Use `AsyncSession`, `await session.execute(...)`, and `async with AsyncSessionLocal()`. Never import or use the synchronous SQLAlchemy session.

**XML field names must be lowercased before access.** `parse_xml_items` normalizes all tags to lowercase. Always access parsed item dicts with lowercase keys (e.g. `item.get("itemcode")`, not `item.get("ItemCode")`). When adding support for a new chain, check what field names it uses and add them to the fallback chains (e.g. `item.get("manufacturername") or item.get("manufacturename")`).

**Store IDs are chain-scoped.** The same `store_id` string (e.g. `"001"`) exists in multiple chains. Always look up stores by `(chain_id, store_id)` together, never by `store_id` alone.

**Product names: first-seen wins.** The product insert is `ON CONFLICT (barcode) DO NOTHING`, so an existing product's name is never updated. This is intentional — don't change it to overwrite names on re-parse.

**Price history via `is_current` flag.** Never delete price rows (the opt-in `HISTORY_RETENTION_DAYS` is the only exception and is off by default). When a price changes, set the old row's `is_current = False` and insert a new row, closing before inserting. When a price is unchanged, only `scraped_at` may be refreshed, and at most once per `TOUCH_INTERVAL_HOURS` (rewriting every unchanged row on every run bloats the table).

**Parser works in chunks of 500 items.** Each chunk is a handful of set-based statements (`PARSE_BATCH_SIZE`). Never go back to one query per row, and keep one transaction per file (data + ledger row), never one per item.

**Schema changes need a migration.** Any schema change (new column, new index) requires a new Alembic migration: `python -m alembic revision --autogenerate -m "description"`. The `pg_trgm` extension is already enabled — don't re-create it. The production API connects as the read-only `api_ro` role, so a new table is readable automatically (default privileges) but any new API *write* needs an explicit grant in a migration.

**Files are deduplicated by name, in two places.** The scraper skips names its status database has verified (`dumps/status`), and the parser skips names whose `ingested_files` row is `done`. Don't change either: re-downloading wastes bandwidth and re-parsing wastes DB writes. Never decide "already loaded" from the presence of a file on disk.

**API responses sort cheapest first.** `/products/{barcode}/compare` and `/basket/compare` both return results ordered by price ascending. Maintain this contract when modifying these endpoints.

**Never mark a file loaded without its data.** The ledger row is written in the same transaction as the prices, and the XML is deleted only after commit. Don't move either step outside the transaction.

**Check XML integrity before parsing.** `il_supermarket_parsers` repairs a truncated file in place and then yields only the items before the cut. `assert_well_formed` must run before the parser reads a file.
