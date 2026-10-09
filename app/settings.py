# app/settings.py
#
# One place for every environment-driven knob. Import values from here instead
# of calling os.getenv all over the code base. Defaults are chosen so a local
# `uvicorn main:app` still works with only DATABASE_URL set.

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    return [p.strip() for p in os.getenv(name, "").split(",") if p.strip()]


# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")
DB_POOL_SIZE = _int("DB_POOL_SIZE", 5)
DB_MAX_OVERFLOW = _int("DB_MAX_OVERFLOW", 5)
# Set when connecting through pgbouncer in transaction mode (e.g. Supabase
# pooler): asyncpg's prepared-statement cache breaks there.
DB_PGBOUNCER = _bool("DB_PGBOUNCER", False)

# ── API ───────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed browser origins. Behind the bundled nginx the
# frontend and API share an origin, so this is only needed when they do not.
FRONTEND_URLS = _list("FRONTEND_URL")
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
DUMPS_DIR = Path(os.getenv("DUMPS_DIR") or PROJECT_ROOT / "dumps").resolve()
# Remove an XML file once it is committed to the database. Off by default so a
# local checkout never loses its raw files; the production compose turns it on.
DELETE_AFTER_INGEST = _bool("DELETE_AFTER_INGEST", False)
MIN_FREE_DISK_GB = _float("MIN_FREE_DISK_GB", 5)

# ── Ingestion worker ──────────────────────────────────────────────────────────
# Download promotion files too. Nothing parses them yet, so by default they are
# not fetched (they would only pile up on disk). Turn on together with a promo loader.
SCRAPE_PROMOS = _bool("SCRAPE_PROMOS", False)
SKIP_BLOCKED_CHAINS = _bool("SKIP_BLOCKED_CHAINS", False)
SCRAPE_CONCURRENCY = _int("SCRAPE_CONCURRENCY", 3)
PARSE_CONCURRENCY = _int("PARSE_CONCURRENCY", 2)
SCRAPE_TIMEOUT_SECONDS = _int("SCRAPE_TIMEOUT_SECONDS", 3 * 3600)
SCRAPE_ATTEMPTS = _int("SCRAPE_ATTEMPTS", 2)
# One cycle per day, local time (SCHEDULE_TIMEZONE). Every cycle downloads the
# chains' full price files; delta files are not used.
RUN_AT = os.getenv("RUN_AT", "06:00")
# A cycle that ended failed/partial is retried this many hours later, up to RETRY_MAX times.
RETRY_AFTER_HOURS = _float("RETRY_AFTER_HOURS", 2)
RETRY_MAX = _int("RETRY_MAX", 2)
SCHEDULE_TIMEZONE = os.getenv("SCHEDULE_TIMEZONE", "Asia/Jerusalem")
# A file that fails to parse this many times is moved to dumps/_quarantine/.
PARSE_MAX_ATTEMPTS = _int("PARSE_MAX_ATTEMPTS", 3)

# ── Price loading ─────────────────────────────────────────────────────────────
PARSE_BATCH_SIZE = 500  # project rule: flush every 500 items
# An unchanged price only gets its scraped_at refreshed, and at most this often.
TOUCH_INTERVAL_HOURS = _float("TOUCH_INTERVAL_HOURS", 24)
# A PriceFull file closes the store's prices it no longer lists, but only when
# it lists at least this share of what we currently hold (guards against a
# truncated or empty file wiping a store).
STALE_CLOSE_MIN_RATIO = _float("STALE_CLOSE_MIN_RATIO", 0.5)
# Optional: drop non-current price rows older than N days. Unset keeps all
# history (the project default).
HISTORY_RETENTION_DAYS = _int("HISTORY_RETENTION_DAYS", 0) or None

# ── Monitoring ────────────────────────────────────────────────────────────────
# Healthchecks.io-style URL: GET <url>/start, <url>, <url>/fail.
HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "").strip() or None
