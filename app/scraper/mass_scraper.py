# app/scraper/mass_scraper.py

import json
import logging
from datetime import datetime
from pathlib import Path

from il_supermarket_scarper.scrapper_runner import MainScrapperRunner
from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.utils.file_types import FileTypesFilters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

FULL_SYNC_INTERVAL_DAYS = 7
FULL_SYNC_TRACKER = Path("dumps/status/full_sync_tracker.json")

# Chains that require an Israeli IP (FTP via publishedprices.co.il).
# These fail gracefully from abroad but work once deployed to an Israeli VPS.
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


def get_enabled_scrapers(skip_blocked: bool = False) -> list[str]:
    all_names = ScraperFactory.all_scrapers_name()
    result = [n for n in all_names if n not in SUPERSEDED]
    if skip_blocked:
        result = [n for n in result if n not in BLOCKED_FROM_ABROAD]
    return result


# ── Full-sync tracker ─────────────────────────────────────────────────────────

def _load_tracker() -> dict:
    if FULL_SYNC_TRACKER.exists():
        return json.loads(FULL_SYNC_TRACKER.read_text())
    return {}


def _save_tracker(tracker: dict):
    FULL_SYNC_TRACKER.parent.mkdir(parents=True, exist_ok=True)
    FULL_SYNC_TRACKER.write_text(json.dumps(tracker, indent=2))


def _needs_full_sync(chain: str, tracker: dict) -> bool:
    last = tracker.get(chain)
    if last is None:
        return True
    return (datetime.now() - datetime.fromisoformat(last)).days >= FULL_SYNC_INTERVAL_DAYS


# ── Runner helper ─────────────────────────────────────────────────────────────

def _run_runner(chains: list[str], workers: int, limit, files_types: list[str]):
    runner = MainScrapperRunner(
        enabled_scrapers=chains,
        output_configuration={
            "output_mode": "disk",
            "base_storage_path": "dumps",
        },
        status_configuration={
            "database_type": "json",
            "base_path": "dumps/status",
        },
        multiprocessing=workers,
    )
    runner.run(
        limit=limit,
        files_types=files_types,
        when_date=None,
        single_pass=True,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def run_mass_scraper(
    chains: list[str] = None,
    limit: int = None,
    skip_blocked: bool = False,
    workers: int = 5,
    force_full: bool = False,
):
    """
    Download price files for all (or selected) chains.

    Strategy per chain:
    - No previous full sync, or last full sync > 7 days ago → PriceFull + PromoFull + Store
    - Recent full sync → Price (delta) + Promo (delta) + Store

    Parameters
    ----------
    chains      : specific scraper names, e.g. ["SHUFERSAL", "VICTORY_NEW_SOURCE"]
    limit       : max files per chain (None = all)
    skip_blocked: skip FTP chains that need an Israeli IP
    workers     : parallel processes
    force_full  : ignore tracker and run a full sync for all chains
    """
    enabled = chains or get_enabled_scrapers(skip_blocked=skip_blocked)
    tracker = _load_tracker()

    if force_full:
        full_chains, delta_chains = enabled, []
    else:
        full_chains = [c for c in enabled if _needs_full_sync(c, tracker)]
        delta_chains = [c for c in enabled if not _needs_full_sync(c, tracker)]

    if full_chains:
        logger.info(f"Full sync ({len(full_chains)} chains): {full_chains}")
        _run_runner(
            full_chains,
            workers,
            limit,
            files_types=[
                FileTypesFilters.STORE_FILE.name,
                FileTypesFilters.PRICE_FULL_FILE.name,
                FileTypesFilters.PROMO_FULL_FILE.name,
            ],
        )
        now = datetime.now().isoformat()
        for c in full_chains:
            tracker[c] = now
        _save_tracker(tracker)

    if delta_chains:
        logger.info(f"Delta sync ({len(delta_chains)} chains): {delta_chains}")
        _run_runner(
            delta_chains,
            workers,
            limit,
            files_types=[
                FileTypesFilters.STORE_FILE.name,
                FileTypesFilters.PRICE_FILE.name,
                FileTypesFilters.PROMO_FILE.name,
            ],
        )

    logger.info("Mass scraper finished.")


if __name__ == "__main__":
    import sys

    # Usage:
    #   python -m app.scraper.mass_scraper                  # all chains, smart delta/full
    #   python -m app.scraper.mass_scraper local            # skip FTP chains
    #   python -m app.scraper.mass_scraper full             # force full sync for all
    #   python -m app.scraper.mass_scraper SHUFERSAL        # one chain

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "local":
        run_mass_scraper(skip_blocked=True)
    elif arg == "full":
        run_mass_scraper(force_full=True)
    elif arg and arg.upper() in ScraperFactory.all_scrapers_name():
        run_mass_scraper(chains=[arg.upper()])
    else:
        run_mass_scraper()
