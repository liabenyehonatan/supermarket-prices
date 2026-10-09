# app/scraper/mass_scraper.py
#
# Downloads price/store/promo files for the Israeli chains via the
# il-supermarket-scraper library into dumps/<Chain>/.
#
# Download dedup is the library's own status database (dumps/status/<chain>.json,
# "verified downloads" by file name), not the presence of the file on disk. That
# is what lets the parser delete a file after loading it without the scraper
# fetching it again. Keep dumps/status on persistent storage.

import logging
from pathlib import Path
from typing import Optional

from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.scrapper_runner import MainScrapperRunner
from il_supermarket_scarper.utils.file_types import FileTypesFilters

from app import settings

logger = logging.getLogger(__name__)


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


def _file_types() -> list[str]:
    """Store lists and full price files. Delta (Price) files are deliberately not used:
    a daily full file is self-correcting, a delta stream can miss changes."""
    types = [FileTypesFilters.STORE_FILE.name, FileTypesFilters.PRICE_FULL_FILE.name]
    if settings.SCRAPE_PROMOS:
        types.append(FileTypesFilters.PROMO_FULL_FILE.name)
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


def scrape_chain(chain: str, *, limit: Optional[int] = None) -> dict:
    """
    Download the new store and full price files of one chain. Files already
    downloaded earlier are skipped by the library's own status database.
    Raises on failure.
    """
    _prune_status(chain)
    logger.info("Scraping %s", chain)
    _run_runner([chain], 1, limit, _file_types())
    return {"chain": chain}


def run_mass_scraper(
    chains: Optional[list[str]] = None,
    limit: Optional[int] = None,
    skip_blocked: bool = False,
    workers: int = 1,  # kept for backwards compatibility; chains run one by one
) -> dict[str, Optional[str]]:
    """
    Scrape the given chains one after another. A failing chain is logged and
    skipped; the return value maps chain -> None (ok) or the error text.
    """
    enabled = chains or get_enabled_scrapers(skip_blocked=skip_blocked)
    outcome: dict[str, Optional[str]] = {}
    for chain in enabled:
        try:
            scrape_chain(chain, limit=limit)
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
    #   python -m app.scraper.mass_scraper                  # all chains
    #   python -m app.scraper.mass_scraper local            # skip the Israel-only chains
    #   python -m app.scraper.mass_scraper SHUFERSAL        # one chain
    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "local":
        results = run_mass_scraper(skip_blocked=True)
    elif arg and arg.upper() in installed_scrapers():
        results = run_mass_scraper(chains=[arg.upper()])
    else:
        results = run_mass_scraper()
    sys.exit(1 if any(results.values()) else 0)
