# app/scraper/run_chain.py
#
# Scrape ONE chain in its own process:
#
#   python -m app.scraper.run_chain SHUFERSAL [--full] [--limit N]
#
# The worker launches this as a subprocess per chain so a hang, crash or leak in
# one chain's scraper can be killed on a timeout without touching the others.
# The last stdout line is a JSON result; the exit code is 0 on success.

import argparse
import json
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("chain")
    parser.add_argument("--full", action="store_true", help="force a full sync")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from app.scraper.mass_scraper import installed_scrapers, scrape_chain

    chain = args.chain.upper()
    if chain not in installed_scrapers():
        print(json.dumps({"chain": chain, "ok": False, "error": "unknown scraper for installed library"}))
        return 1
    try:
        result = scrape_chain(chain, force_full=args.full, limit=args.limit)
    except Exception as exc:
        logging.exception("scrape failed")
        print(json.dumps({"chain": chain, "ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 1
    print(json.dumps({**result, "ok": True}))
    return 0


# The guard is required: the scraper library starts child processes, and on
# macOS/Windows those re-import this module.
if __name__ == "__main__":
    sys.exit(main())
