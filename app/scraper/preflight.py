# app/scraper/preflight.py
#
# "Can THIS machine reach every chain?" Downloads one small Stores file per
# chain into a throw-away directory and prints a table. Run it on a new server
# before relying on it:
#
#   python -m app.scraper.preflight                 # every chain
#   python -m app.scraper.preflight RAMI_LEVY YELLOW
#
# Exit code is non-zero when any chain could not be fetched.

import signal
import sys
import tempfile
import time
from pathlib import Path

PER_CHAIN_TIMEOUT = 180


class _Timeout(Exception):
    pass


def _alarm(*_):
    raise _Timeout(f"no answer in {PER_CHAIN_TIMEOUT}s")


def main() -> int:
    from il_supermarket_scarper.utils.file_types import FileTypesFilters
    from il_supermarket_scarper.utils.folders_name import DumpFolderNames

    from app.scraper.mass_scraper import (
        BLOCKED_FROM_ABROAD, _run_runner, get_enabled_scrapers, installed_scrapers,
    )

    wanted = [a.upper() for a in sys.argv[1:]] or get_enabled_scrapers()
    known = set(installed_scrapers())
    signal.signal(signal.SIGALRM, _alarm)

    rows, failures = [], 0
    with tempfile.TemporaryDirectory(prefix="scrape-preflight-") as tmp:
        for chain in wanted:
            if chain not in known:
                rows.append((chain, "SKIP", "not in installed library"))
                continue
            started = time.time()
            signal.alarm(PER_CHAIN_TIMEOUT)
            try:
                _run_runner([chain], 1, 1, [FileTypesFilters.STORE_FILE.name], base_path=Path(tmp))
                # Each chain downloads into its own folder; check only that one.
                chain_dir = Path(tmp) / DumpFolderNames[chain].value
                got = [p for p in chain_dir.glob("*") if p.is_file()] if chain_dir.is_dir() else []
                status = "OK" if got else "EMPTY"
                detail = f"{time.time() - started:.1f}s, {len(got)} file"
                if status == "EMPTY":
                    failures += 1
            except BaseException as exc:  # includes the alarm timeout
                status, detail = "FAIL", f"{type(exc).__name__}: {str(exc)[:80]}"
                failures += 1
            finally:
                signal.alarm(0)
            rows.append((chain, status, detail + ("  [IL-only chain]" if chain in BLOCKED_FROM_ABROAD else "")))

    width = max(len(r[0]) for r in rows)
    for chain, status, detail in rows:
        print(f"{chain:<{width}}  {status:<5}  {detail}")
    print(f"\n{len(rows) - failures} reachable, {failures} problems")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
