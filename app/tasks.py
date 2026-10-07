import asyncio
import logging

from app.celery_app import app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@app.task(bind=True, name="app.tasks.scrape_all")
def scrape_all(self, chains=None, skip_blocked=True, workers=5):
    """Download price/store XML files for all (or selected) chains."""
    from app.scraper.mass_scraper import run_mass_scraper

    logger.info(f"[Task {self.request.id}] Starting mass scraper")
    self.update_state(state="SCRAPING")
    run_mass_scraper(chains=chains, skip_blocked=skip_blocked, workers=workers)
    logger.info(f"[Task {self.request.id}] Scraper finished")
    return {"status": "done", "task": "scrape_all"}


@app.task(bind=True, name="app.tasks.parse_all")
def parse_all(self, chains=None):
    """Parse all downloaded XML files into PostgreSQL."""
    from app.parser.mass_parser import run_mass_parser

    logger.info(f"[Task {self.request.id}] Starting mass parser")
    self.update_state(state="PARSING")
    _run_async(run_mass_parser(chains=chains))
    logger.info(f"[Task {self.request.id}] Parser finished")
    return {"status": "done", "task": "parse_all"}


@app.task(bind=True, name="app.tasks.scrape_and_parse")
def scrape_and_parse(self, chains=None, skip_blocked=True, workers=5):
    """Full pipeline: scrape then parse."""
    from app.scraper.mass_scraper import run_mass_scraper
    from app.parser.mass_parser import run_mass_parser

    logger.info(f"[Task {self.request.id}] Starting scrape-and-parse pipeline")

    self.update_state(state="SCRAPING")
    run_mass_scraper(chains=chains, skip_blocked=skip_blocked, workers=workers)

    self.update_state(state="PARSING")
    _run_async(run_mass_parser(chains=chains))

    logger.info(f"[Task {self.request.id}] Pipeline finished")
    return {"status": "done", "task": "scrape_and_parse"}
