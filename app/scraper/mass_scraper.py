# app/scraper/mass_scraper.py
#
# Downloads price/store/promo files for the Israeli chains via the
# il-supermarket-scraper library into dumps/<Chain>/.
#
# Download dedup is the library's own status database (dumps/status/<chain>.json,
# "verified downloads" by file name), not the presence of the file on disk. That
# is what lets the parser delete a file after loading it without the scraper
# fetching it again. Keep dumps/status on persistent storage.

import fcntl
import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.scrapper_runner import MainScrapperRunner
from il_supermarket_scarper.utils.file_types import FileTypesFilters

from app import settings

logger = logging.getLogger(__name__)

FULL_SYNC_INTERVAL_DAYS = settings.FULL_SYNC_INTERVAL_DAYS
STATUS_DIR = settings.DUMPS_DIR / "status"
FULL_SYNC_TRACKER = STATUS_DIR / "full_sync_tracker.json"

# Chains served from FTP hosts (publishedprices.co.il) that refuse non-Israeli
# addresses. They fail gracefully from abroad and work from an Israeli IP.
BLOCKED_FROM_ABROAD = {
    "RAMI_LEVY",
    "OSHER_AD",
    "YOHANANOF",
    "TIV_TAAM",
    "COFIX",
    "DOR_ALON",
    "KESHET",
    "POLIZER",
    "SALACH_DABACH",
    "STOP_MARKET",
    "SUPER_YUDA",
    "FRESH_MARKET_AND_SUPER_DOSH",
    "YELLOW",
}

# Use the newer REST API source for Victory instead of the legacy ASPX scraper.
SUPERSEDED = {"VICTORY"}


def installed_scrapers() -> list[str]:
    """Scraper names the installed library version actually knows."""
    return list(ScraperFactory.all_scrapers_name())


def get_enabled_scrapers(skip_blocked: bool = False) -> list[str]:
    result = [n for n in installed_scrapers() if n not in SUPERSEDED]
    if skip_blocked:
        result = [n for n in result if n not in BLOCKED_FROM_ABROAD]
    return result


# ── Full-sync tracker ─────────────────────────────────────────────────────────
# Several chain scrapes may run at once (one process each), so every change is
# a locked read-modify-write and the file is replaced atomically.

@contextmanager
def _tracker_lock():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATUS_DIR / ".tracker.lock", "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _load_tracker() -> dict:
    try:
        return json.loads(FULL_SYNC_TRACKER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _mark_full_sync(chain: str) -> None:
    with _tracker_lock():
        tracker = _load_tracker()
        tracker[chain] = datetime.now().isoformat()
        tmp = FULL_SYNC_TRACKER.with_suffix(".tmp")
        tmp.write_text(json.dumps(tracker, indent=2))
        os.replace(tmp, FULL_SYNC_TRACKER)


def _needs_full_sync(chain: str, tracker: dict) -> bool:
    last = tracker.get(chain)
    if last is None:
        return True
    return (datetime.now() - datetime.fromisoformat(last)).days >= FULL_SYNC_INTERVAL_DAYS


# ── Runner helper ─────────────────────────────────────────────────────────────

def _run_runner(
    chains: list[str],
    workers: int,
    limit: Optional[int],
    files_types: list[str],
    base_path: Optional[Path] = None,
):
    base = Path(base_path) if base_path else settings.DUMPS_DIR
    runner = MainScrapperRunner(
        enabled_scrapers=chains,
        output_configuration={
            "output_mode": "disk",
            "base_storage_path": str(base),
        },
        status_configuration={
            "database_type": "json",
            "base_path": str(base / "status"),
        },
        multiprocessing=workers,
    )
    runner.run(
        limit=limit,
        files_types=files_types,
        when_date=None,
        single_pass=True,
    )


def _file_types(full: bool) -> list[str]:
    types = [
        FileTypesFilters.STORE_FILE.name,
        (FileTypesFilters.PRICE_FULL_FILE if full else FileTypesFilters.PRICE_FILE).name,
    ]
    if settings.SCRAPE_PROMOS:
        types.append((FileTypesFilters.PROMO_FULL_FILE if full else FileTypesFilters.PROMO_FILE).name)
    return types


# ── Public API ────────────────────────────────────────────────────────────────

def _prune_status(chain: str) -> None:
    """Keep the library's per-chain JSON from growing forever. Never fatal."""
    try:
        from il_supermarket_scarper.utils.folders_name import DumpFolderNames

        from app.scraper import status_store

        status_store.prune(DumpFolderNames[chain].value)
    except Exception as exc:
        logger.warning("could not prune scraper status for %s: %s", chain, exc)


def scrape_chain(
    chain: str,
    *,
    force_full: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """
    Download one chain. Full files if it has none yet or the last full sync is
    older than FULL_SYNC_INTERVAL_DAYS (or force_full), otherwise only deltas.

    The chain is recorded as fully synced only when the download completed
    without raising; a crash or timeout leaves it due for a full sync again.
    Raises on failure.
    """
    full = force_full or _needs_full_sync(chain, _load_tracker())
    _prune_status(chain)
    logger.info("Scraping %s (%s)", chain, "full" if full else "delta")
    _run_runner([chain], 1, limit, _file_types(full))
    if full:
        _mark_full_sync(chain)
    return {"chain": chain, "mode": "full" if full else "delta"}


def run_mass_scraper(
    chains: Optional[list[str]] = None,
    limit: Optional[int] = None,
    skip_blocked: bool = False,
    workers: int = 1,  # kept for backwards compatibility; chains run one by one
    force_full: bool = False,
) -> dict[str, Optional[str]]:
    """
    Scrape the given chains one after another. A failing chain is logged and
    skipped; the return value maps chain -> None (ok) or the error text.
    """
    enabled = chains or get_enabled_scrapers(skip_blocked=skip_blocked)
    outcome: dict[str, Optional[str]] = {}
    for chain in enabled:
        try:
            scrape_chain(chain, force_full=force_full, limit=limit)
            outcome[chain] = None
        except Exception as exc:
            logger.exception("Scrape of %s failed", chain)
            outcome[chain] = f"{type(exc).__name__}: {exc}"
    failed = [c for c, e in outcome.items() if e]
    logger.info("Mass scraper finished: %d ok, %d failed %s", len(outcome) - len(failed), len(failed), failed)
    return outcome


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Usage:
    #   python -m app.scraper.mass_scraper                  # all chains, smart delta/full
    #   python -m app.scraper.mass_scraper local            # skip FTP chains
    #   python -m app.scraper.mass_scraper full             # force full sync for all
    #   python -m app.scraper.mass_scraper SHUFERSAL        # one chain
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "local":
        results = run_mass_scraper(skip_blocked=True)
    elif arg == "full":
        results = run_mass_scraper(force_full=True)
    elif arg and arg.upper() in installed_scrapers():
        results = run_mass_scraper(chains=[arg.upper()])
    else:
        results = run_mass_scraper()
    sys.exit(1 if any(results.values()) else 0)
