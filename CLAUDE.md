# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the API server
uvicorn main:app --reload

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Run scrapers
python -m app.scraper.scraper_service          # Shufersal (Playwright)
python -m app.scraper.mass_scraper             # Multi-chain via il-supermarket-scraper

# Run parsers
python -m app.parser.parser_service            # Shufersal GZ files
python -m app.parser.parser_service victory    # Victory GZ files

# Celery worker (runs tasks)
celery -A app.celery_app worker --loglevel=info

# Celery Beat (schedules tasks every 3h + nightly)
celery -A app.celery_app beat --loglevel=info

# Both in one process (development only)
celery -A app.celery_app worker --beat --loglevel=info

# Tests
pytest
```

Environment: requires a `.env` file with `DATABASE_URL` (async PostgreSQL URL, e.g. `postgresql+asyncpg://...`).

## Architecture

**Data pipeline:** Scraper → `dumps/<Chain>/` (GZ files) → Parser → PostgreSQL → FastAPI

### Scraper layer (`app/scraper/`)
- `scraper_service.py`: Playwright-based scraper for Shufersal's price portal. Navigates paginated file listings and downloads GZ files to `dumps/Shufersal/`.
- `mass_scraper.py`: Uses the `il-supermarket-scraper` library to pull from multiple chains at once.
- `victory_scraper.py`: Chain-specific scraper for Victory.
- Downloaded files are skipped if they already exist on disk (filename deduplication).

### Parser layer (`app/parser/`)
- `parser_service.py`: Core parser. Reads GZ→XML with `iterparse` (streaming, memory-efficient). Normalizes all XML tag names to lowercase to handle field name variations across chains (e.g. `ManufacturerName` vs `ManufactureName`, `UnitOfMeasure` vs `UnitMeasure`). Commits in batches of 500 items.
- `universal_parser.py` / `mass_parser.py`: Multi-chain parsing wrappers.
- **Price history strategy**: each price row has `is_current`. On a price change, the old row is set `is_current=False` and a new row is inserted. Unchanged prices just get their `scraped_at` updated.

### Database (`app/db/`)
Five tables: `chains` → `stores` → `prices` ← `products`, and `promotions`.
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

### Task queue (`app/celery_app.py`, `app/tasks.py`)
Celery + Redis. Three tasks: `scrape_all`, `parse_all`, `scrape_and_parse` (full pipeline). Beat schedule runs `scrape_and_parse` every 3 hours (skipping blocked FTP chains) and a full scrape at 2 AM nightly. API endpoints at `/api/v1/tasks/*` allow triggering tasks on demand and checking status by task ID.

## Rules

**Money is always `Decimal`/`Numeric(10, 2)`.** Never use `float` for prices. `6.50 + 3.30` in float gives `9.799999...`. Use `Decimal` in Python and `Numeric(10, 2)` in SQLAlchemy columns.

**All DB access must be async.** Use `AsyncSession`, `await session.execute(...)`, and `async with AsyncSessionLocal()`. Never import or use the synchronous SQLAlchemy session.

**XML field names must be lowercased before access.** `parse_xml_items` normalizes all tags to lowercase. Always access parsed item dicts with lowercase keys (e.g. `item.get("itemcode")`, not `item.get("ItemCode")`). When adding support for a new chain, check what field names it uses and add them to the fallback chains (e.g. `item.get("manufacturername") or item.get("manufacturename")`).

**Store IDs are chain-scoped.** The same `store_id` string (e.g. `"001"`) exists in multiple chains. Always look up stores by `(chain_id, store_id)` together, never by `store_id` alone.

**Product names: first-seen wins.** `get_or_create_product` does not update an existing product's name. This is intentional — don't change it to overwrite names on re-parse.

**Price history via `is_current` flag.** Never delete price rows. When a price changes, set the old row's `is_current = False` and insert a new row. When a price is unchanged, only update `scraped_at`.

**Parser batches at 500 items.** Call `await session.flush()` every 500 items inside the parse loop. Don't commit per-item (too slow) and don't defer everything to the end (risky for large files).

**New chains need a migration.** Any schema change (new column, new index) requires a new Alembic migration: `alembic revision --autogenerate -m "description"`. The `pg_trgm` extension is already enabled — don't re-create it.

**Scraper files are deduplicated by filename.** `run_scraper` skips files that already exist in `dumps/<Chain>/`. Don't change this behavior — re-downloading identical GZ files wastes bandwidth and re-parsing them wastes DB writes.

**API responses sort cheapest first.** `/products/{barcode}/compare` and `/basket/compare` both return results ordered by price ascending. Maintain this contract when modifying these endpoints.
