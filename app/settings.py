# app/settings.py
#
# One place for every environment-driven knob. Import values from here instead
# of calling os.getenv all over the code base. Defaults are chosen so a local
# `uvicorn main:app` still works with only DATABASE_URL set.

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    """
    The variable's value without an inline "  # comment". docker compose hands the
    raw text after "=" to the container, so `KEY=2   # note` arrives as "2   # note".
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def _int(name: str, default: int) -> int:
    raw = _env(name)
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = _env(name)
    return float(raw) if raw else default


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    return [p.strip() for p in _env(name).split(",") if p.strip()]


# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = _env("DATABASE_URL") or None
DB_POOL_SIZE = _int("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW = _int("DB_MAX_OVERFLOW", 5)
# Set when connecting through pgbouncer in transaction mode (e.g. Supabase
# pooler): asyncpg's prepared-statement cache breaks there.
DB_PGBOUNCER = _bool("DB_PGBOUNCER", False)

# ── API ───────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed browser origins. Behind the bundled nginx the
# frontend and API share an origin, so this is only needed when they do not.
FRONTEND_URLS = _list("FRONTEND_URL")
# The site's public address (https://example.com). When set, canonical links, the sitemap and link previews use it
# whatever address a request came in on (IP, www, domain); when empty they follow the request.
SITE_URL = _env("SITE_URL").rstrip("/")
# Where the API fetches the built page shell (index.html) to put each page's own title, description,
# canonical link and structured data into it.
SEO_SHELL_URL = _env("SEO_SHELL_URL") or "http://frontend:80/index.html"
DEV_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
# /health/data answers 503 when the last successful ingest is older than this
# (one daily run, so a day plus a retry window).
MAX_DATA_AGE_HOURS = _float("MAX_DATA_AGE_HOURS", 36)

# ── Files ─────────────────────────────────────────────────────────────────────
DUMPS_DIR = Path(_env("DUMPS_DIR") or PROJECT_ROOT / "dumps").resolve()
# Remove an XML file once it is committed to the database. Off by default so a
# local checkout never loses its raw files; the production compose turns it on.
DELETE_AFTER_INGEST = _bool("DELETE_AFTER_INGEST", False)
MIN_FREE_DISK_GB = _float("MIN_FREE_DISK_GB", 5)

# ── Ingestion worker ──────────────────────────────────────────────────────────
# Download and load promotion files. Off by default: they take disk and database space.
SCRAPE_PROMOS = _bool("SCRAPE_PROMOS", False)
# Limit promotions to these chains (scraper names, comma separated). Empty = every chain.
PROMO_CHAINS = {c.upper() for c in _list("PROMO_CHAINS")}


def promos_enabled_for(chain: str) -> bool:
    """Whether promotion files are downloaded and loaded for this chain (a ScraperFactory name)."""
    return SCRAPE_PROMOS and (not PROMO_CHAINS or chain.upper() in PROMO_CHAINS)


SKIP_BLOCKED_CHAINS = _bool("SKIP_BLOCKED_CHAINS", False)
# Scraper names never run by the schedule (comma separated, e.g. SUPER_PHARM). For a
# chain that fails every time on this server, so it does not mark every cycle "partial".
# Naming a chain explicitly (--chains, preflight arguments) still works.
SKIP_CHAINS = {c.upper() for c in _list("SKIP_CHAINS")}
SCRAPE_CONCURRENCY = _int("SCRAPE_CONCURRENCY", 3)
PARSE_CONCURRENCY = _int("PARSE_CONCURRENCY", 2)
SCRAPE_TIMEOUT_SECONDS = _int("SCRAPE_TIMEOUT_SECONDS", 3 * 3600)
SCRAPE_ATTEMPTS = _int("SCRAPE_ATTEMPTS", 2)
# Daily cycle times, local time (SCHEDULE_TIMEZONE), comma separated. Every cycle
# downloads only the full price files published since the previous one; delta
# files are not used. Chains that publish in the afternoon are picked up by the
# evening cycle.
RUN_AT = _env("RUN_AT", "06:00,18:00") or "06:00,18:00"
# A cycle that ended failed/partial is retried this many hours later, up to RETRY_MAX times.
RETRY_AFTER_HOURS = _float("RETRY_AFTER_HOURS", 2)
RETRY_MAX = _int("RETRY_MAX", 2)
SCHEDULE_TIMEZONE = _env("SCHEDULE_TIMEZONE", "Asia/Jerusalem") or "Asia/Jerusalem"
# A file that fails to parse this many times is moved to dumps/_quarantine/.
PARSE_MAX_ATTEMPTS = _int("PARSE_MAX_ATTEMPTS", 3)

# ── Price loading ─────────────────────────────────────────────────────────────
PARSE_BATCH_SIZE = 500  # project rule: flush every 500 items
# A PriceFull file closes the store's prices it no longer lists, but only when
# it lists at least this share of what we currently hold (guards against a
# truncated or empty file wiping a store).
STALE_CLOSE_MIN_RATIO = _float("STALE_CLOSE_MIN_RATIO", 0.5)
# Optional: drop non-current price rows older than N days. Unset keeps all
# history (the project default).
HISTORY_RETENTION_DAYS = _int("HISTORY_RETENTION_DAYS", 0) or None

# After each cycle the worker looks up pictures for the most-searched products that have none yet,
# for up to this many minutes (0 turns it off). Lookups go to Shufersal's site, a few at a time.
IMAGE_FILL_MINUTES = _float("IMAGE_FILL_MINUTES", 30)

# Then, for what Shufersal does not carry, Open Food Facts is asked (two at a time, about 20 a minute),
# the promotions section's products first. 0 turns it off.
OFF_IMAGE_FILL_MINUTES = _float("OFF_IMAGE_FILL_MINUTES", 20)

# After each cycle the worker finds positions for stores that have none yet, for up to this many
# minutes (0 turns it off). Uses OpenStreetMap's Nominatim, one request per second.
GEOCODE_MINUTES = _float("GEOCODE_MINUTES", 10)

# ── Monitoring ────────────────────────────────────────────────────────────────
# Healthchecks.io-style URL: GET <url>/start, <url>, <url>/fail.
# A chain with no full price file loaded for this many days is reported (a few days: chains skip holidays).
STALE_CHAIN_DAYS = _float("STALE_CHAIN_DAYS", 5)
HEALTHCHECK_URL = _env("HEALTHCHECK_URL") or None
# Optional 4th healthchecks.io check: pinged after each cycle, /fail with the list when a chain looks dead.
HEALTHCHECK_CHAINS_URL = _env("HEALTHCHECK_CHAINS_URL") or None
