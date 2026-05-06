# app/scraper/mass_scraper.py

import logging
from il_supermarket_scarper.scrapper_runner import MainScrapperRunner
from il_supermarket_scarper import ScraperFactory
from il_supermarket_scarper.utils.file_types import FileTypesFilters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Chains that need an Israeli IP (FTP-based). They will fail gracefully
# when run from outside Israel, but are included so the runner doesn't skip them.
BLOCKED_FROM_ABROAD = {
    "RAMI_LEVY",
    "OSHER_AD",
    "YOHANANOF",
    "TIV_TAAM",
    "HAZI_HINAM",
    "MAHSANI_ASHUK",
    "NETIV_HASED",
    "ZOL_VEBEGADOL",
}


def get_enabled_scrapers(skip_blocked: bool = False) -> list[str]:
    """
    Return the list of all active scraper names.
    If skip_blocked=True, exclude chains that require an Israeli IP.
    """
    all_names = ScraperFactory.all_scrapers_name()
    if skip_blocked:
        return [n for n in all_names if n not in BLOCKED_FROM_ABROAD]
    return all_names


def run_mass_scraper(
    chains: list[str] = None,
    limit: int = None,
    skip_blocked: bool = False,
    workers: int = 5,
):
    """
    Download price+store files for all (or selected) Israeli supermarket chains.

    Uses MainScrapperRunner which handles each chain's source type automatically:
    - Playwright (Shufersal)
    - HTTP portals (Victory, Cofix, …)
    - FTP servers (RamiLevy, OsherAd, Yohananof — need Israeli IP)

    Files are saved to dumps/<ChainFolder>/<filename>.xml

    Parameters
    ----------
    chains : list of ScraperFactory enum names, e.g. ["SHUFERSAL", "VICTORY"]
             None = all active chains
    limit  : max files per chain (None = all available)
    skip_blocked : if True, skip FTP chains that need Israeli IP
    workers : parallel processes (default 5)
    """
    enabled = chains or get_enabled_scrapers(skip_blocked=skip_blocked)
    logger.info(f"Starting mass scraper for {len(enabled)} chains: {enabled}")

    runner = MainScrapperRunner(
        enabled_scrapers=enabled,
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
        files_types=[
            FileTypesFilters.PRICE_FULL_FILE,
            FileTypesFilters.STORE_FILE,
        ],
        single_pass=True,
    )

    logger.info("Mass scraper finished.")


if __name__ == "__main__":
    import sys

    # Usage:
    #   python -m app.scraper.mass_scraper             # all chains
    #   python -m app.scraper.mass_scraper local       # skip FTP chains
    #   python -m app.scraper.mass_scraper SHUFERSAL   # one chain

    arg = sys.argv[1] if len(sys.argv) > 1 else None

    if arg == "local":
        run_mass_scraper(skip_blocked=True)
    elif arg and arg.upper() in ScraperFactory.all_scrapers_name():
        run_mass_scraper(chains=[arg.upper()])
    else:
        run_mass_scraper()
