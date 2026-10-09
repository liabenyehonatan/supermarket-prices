# app/worker.py
#
# The ingestion worker: keeps the database fed from the chains' price portals.
#
#   python -m app.worker                     # run forever on the schedule
#   python -m app.worker --once              # one cycle, then exit
#   python -m app.worker --once --chains SHUFERSAL RAMI_LEVY
#   python -m app.worker --once --no-scrape  # only load what is already in dumps/
#
# Design
#  - One cycle at a time, guarded by a Postgres advisory lock (safe across
#    containers/hosts; frees itself if the process dies).
#  - Every chain is isolated: its scrape runs in its own subprocess with a
#    timeout and retries, its parse is its own task. A failure in one chain is
#    recorded and never stops the others.
#  - Every cycle and chain/phase is written to ingest_runs; an optional
#    healthchecks.io-style URL gets start / success / fail pings.

import argparse
import asyncio
import json
import logging
import os
import shutil
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from app import settings
from app.parser.mass_parser import ChainParseResult, chains_on_disk, folder_for_chain, parse_chain
from app.pipeline import maintenance, runs
from app.pipeline.lock import AlreadyRunning, ingest_lock
from app.pipeline.shutdown import STOP
from app.scraper.mass_scraper import get_enabled_scrapers, installed_scrapers

logger = logging.getLogger("worker")


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class ChainOutcome:
    chain: str
    scrape_ok: Optional[bool] = None          # None = scrape not attempted
    scrape_error: Optional[str] = None
    parse: Optional[ChainParseResult] = None
    parse_error: Optional[str] = None

    @property
    def ok(self) -> bool:
        scrape_fine = self.scrape_ok is not False
        parse_fine = self.parse_error is None and (self.parse is None or self.parse.status == "ok")
        return scrape_fine and parse_fine

    @property
    def failed(self) -> bool:
        parsed_something = self.parse is not None and self.parse.files_ok > 0
        return (self.scrape_ok is False and not parsed_something) or (
            self.parse_error is not None
        ) or (self.parse is not None and self.parse.status == "failed")


@dataclass
class CycleSummary:
    status: str = "ok"
    outcomes: list[ChainOutcome] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def failed_chains(self) -> list[str]:
        return [o.chain for o in self.outcomes if not o.ok]


# ── Scrape: one subprocess per chain ──────────────────────────────────────────

async def _kill_group(proc: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # the library spawns child processes
    except ProcessLookupError:
        pass
    await proc.wait()


def _scrape_command(chain: str) -> list[str]:
    return [sys.executable, "-m", "app.scraper.run_chain", chain]


async def scrape_in_subprocess(chain: str) -> tuple[bool, Optional[str]]:
    """Run app.scraper.run_chain with a timeout and retries. Returns (ok, error)."""
    last_error = "unknown"
    for attempt in range(1, settings.SCRAPE_ATTEMPTS + 1):
        if STOP.is_set():
            return False, "stopped"
        proc = await asyncio.create_subprocess_exec(
            *_scrape_command(chain),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(settings.PROJECT_ROOT),
            start_new_session=True,  # own process group so we can kill the whole tree
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=settings.SCRAPE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await _kill_group(proc)
            last_error = f"timed out after {settings.SCRAPE_TIMEOUT_SECONDS}s"
        except asyncio.CancelledError:
            await _kill_group(proc)
            raise
        else:
            text = out.decode("utf-8", "replace")
            if proc.returncode == 0:
                return True, None
            tail = " | ".join(line.strip() for line in text.strip().splitlines()[-3:])
            last_error = f"exit {proc.returncode}: {tail}"[:500]
        logger.warning("%s scrape attempt %d/%d failed: %s", chain, attempt, settings.SCRAPE_ATTEMPTS, last_error)
        if attempt < settings.SCRAPE_ATTEMPTS:
            await asyncio.sleep(30 * attempt)
    return False, last_error


# ── One chain: scrape then parse ──────────────────────────────────────────────

async def process_chain(
    chain: str,
    cycle_id: Optional[int],
    scrape_sem: asyncio.Semaphore,
    parse_sem: asyncio.Semaphore,
    *,
    scrape: bool,
    parse: bool,
    scrape_allowed: bool,
) -> ChainOutcome:
    outcome = ChainOutcome(chain=chain)

    if scrape:
        if not scrape_allowed:
            outcome.scrape_ok, outcome.scrape_error = False, "skipped: low disk space"
        else:
            async with scrape_sem:
                run_id = await runs.start_run("scrape", chain, cycle_id)
                ok, error = await scrape_in_subprocess(chain)
                outcome.scrape_ok, outcome.scrape_error = ok, error
                await runs.finish_run(run_id, "ok" if ok else "failed", error=error)

    if parse and not STOP.is_set():
        async with parse_sem:
            run_id = await runs.start_run("parse", chain, cycle_id)
            try:
                result = await parse_chain(chain)
                outcome.parse = result
                await runs.finish_run(
                    run_id, result.status,
                    files_ok=result.files_ok,
                    files_failed=result.files_failed + result.files_quarantined,
                    rows_applied=result.rows_applied,
                    error="; ".join(result.errors[:5]) or None,
                )
            except Exception as exc:  # parse_chain handles data errors; this is infrastructure
                logger.exception("%s parse crashed", chain)
                outcome.parse_error = f"{type(exc).__name__}: {exc}"
                await runs.finish_run(run_id, "failed", error=outcome.parse_error)
    return outcome


# ── Notifications ─────────────────────────────────────────────────────────────

async def ping(suffix: str = "") -> None:
    if not settings.HEALTHCHECK_URL:
        return
    url = settings.HEALTHCHECK_URL.rstrip("/") + suffix
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(url)
    except Exception as exc:
        logger.warning("healthcheck ping %s failed: %s", suffix or "/", exc)


# ── One cycle ─────────────────────────────────────────────────────────────────

def _disk_ok() -> bool:
    settings.DUMPS_DIR.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(settings.DUMPS_DIR).free / 1e9
    if free_gb < settings.MIN_FREE_DISK_GB:
        logger.error("Only %.1f GB free in %s (< %.1f); not downloading", free_gb, settings.DUMPS_DIR, settings.MIN_FREE_DISK_GB)
        return False
    return True


def resolve_chains(requested: Optional[list[str]], scrape: bool) -> tuple[list[str], list[str]]:
    """(chains to run, notes about requested names that were dropped)."""
    notes: list[str] = []
    known = set(installed_scrapers())
    if requested:
        chains = [c for c in requested if c in known]
        notes += [f"unknown chain {c} ignored" for c in requested if c not in known]
    elif scrape:
        chains = get_enabled_scrapers(skip_blocked=settings.SKIP_BLOCKED_CHAINS)
    else:
        chains = chains_on_disk()
    runnable = []
    for chain in chains:
        try:
            folder_for_chain(chain)
            runnable.append(chain)
        except KeyError:
            notes.append(f"{chain} has no dump folder mapping; skipped")
    return runnable, notes


async def run_cycle(
    chains: Optional[list[str]] = None,
    *,
    scrape: bool = True,
    parse: bool = True,
) -> CycleSummary:
    """One scrape+parse pass. Raises AlreadyRunning if another run holds the lock."""
    summary = CycleSummary()
    async with ingest_lock():
        abandoned = await runs.close_abandoned_runs()
        if abandoned:
            summary.notes.append(f"closed {abandoned} abandoned run rows")

        todo, notes = resolve_chains(chains, scrape)
        summary.notes += notes
        cycle_id = await runs.start_run("cycle")
        await ping("/start")
        logger.info("Cycle start: %d chains (scrape=%s parse=%s)", len(todo), scrape, parse)

        scrape_allowed = _disk_ok() if scrape else True
        if scrape and not scrape_allowed:
            summary.notes.append("downloads skipped: low disk space")

        scrape_sem = asyncio.Semaphore(settings.SCRAPE_CONCURRENCY)
        parse_sem = asyncio.Semaphore(settings.PARSE_CONCURRENCY)
        tasks = [
            asyncio.create_task(process_chain(
                c, cycle_id, scrape_sem, parse_sem,
                scrape=scrape, parse=parse, scrape_allowed=scrape_allowed,
            ))
            for c in todo
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for chain, item in zip(todo, gathered):
            if isinstance(item, BaseException):
                logger.error("%s: unexpected crash: %r", chain, item)
                summary.outcomes.append(ChainOutcome(chain=chain, parse_error=f"crash: {item!r}"))
            else:
                summary.outcomes.append(item)

        ok_count = sum(1 for o in summary.outcomes if o.ok)
        failed_count = sum(1 for o in summary.outcomes if o.failed)
        if not summary.outcomes or ok_count == len(summary.outcomes):
            summary.status = "ok"
        elif failed_count == len(summary.outcomes):
            summary.status = "failed"
        else:
            summary.status = "partial"
        if not scrape_allowed:
            summary.status = "failed" if summary.status == "ok" else summary.status

        # Housekeeping never decides the cycle result.
        try:
            if settings.HISTORY_RETENTION_DAYS:
                await maintenance.prune_history(settings.HISTORY_RETENTION_DAYS)
            await runs.purge_old_runs()
            await runs.purge_old_ledger()
        except Exception as exc:
            logger.warning("housekeeping failed: %s", exc)

        files_ok = sum(o.parse.files_ok for o in summary.outcomes if o.parse)
        files_failed = sum(o.parse.files_failed + o.parse.files_quarantined for o in summary.outcomes if o.parse)
        rows = sum(o.parse.rows_applied for o in summary.outcomes if o.parse)
        await runs.finish_run(
            cycle_id, summary.status,
            files_ok=files_ok, files_failed=files_failed, rows_applied=rows,
            error=("failed chains: " + ", ".join(summary.failed_chains))[:4000] if summary.failed_chains else None,
        )
        await ping("" if summary.status in ("ok", "partial") else "/fail")
        logger.info(
            "Cycle %s: %d/%d chains ok, %d files loaded, %d rows applied%s",
            summary.status, ok_count, len(summary.outcomes), files_ok, rows,
            f"; problems: {summary.failed_chains}" if summary.failed_chains else "",
        )
    return summary


# ── Schedule ──────────────────────────────────────────────────────────────────

def _run_times() -> list[tuple[int, int]]:
    """RUN_AT ("06:00,18:00") as sorted (hour, minute) pairs."""
    times = sorted({tuple(int(p) for p in part.strip().split(":")) for part in settings.RUN_AT.split(",") if part.strip()})
    if not times:
        raise ValueError("RUN_AT must hold at least one HH:MM time")
    return times


def next_slot(now: datetime) -> datetime:
    """The next RUN_AT time after `now`, in now's timezone."""
    candidates = []
    for day in (0, 1):
        for hour, minute in _run_times():
            slot = (now + timedelta(days=day)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if slot > now:
                candidates.append(slot)
    return min(candidates)


def longest_gap_hours() -> float:
    """Longest wait between two consecutive runs; older data than this means a run was missed."""
    minutes = [h * 60 + m for h, m in _run_times()]
    gaps = [b - a for a, b in zip(minutes, minutes[1:])] + [minutes[0] + 24 * 60 - minutes[-1]]
    return max(gaps) / 60


async def serve() -> None:
    tz = ZoneInfo(settings.SCHEDULE_TIMEZONE)
    logger.info("Worker started: cycles daily at %s (%s)", settings.RUN_AT, settings.SCHEDULE_TIMEZONE)

    # Run at startup if a scheduled run was missed (data older than the longest gap), otherwise wait.
    try:
        age = await runs.data_age_hours()
    except Exception as exc:
        logger.warning("could not read data age (%s); running now", exc)
        age = None
    run_now = age is None or age > longest_gap_hours() + 1
    retries = 0

    while not STOP.is_set():
        wake = None
        if run_now:
            try:
                summary = await run_cycle()
                if summary.status == "ok":
                    retries = 0
                elif retries < settings.RETRY_MAX:
                    retries += 1
                    wake = datetime.now(tz) + timedelta(hours=settings.RETRY_AFTER_HOURS)
                    logger.warning("Cycle %s; retry %d/%d at %s", summary.status, retries,
                                   settings.RETRY_MAX, wake.isoformat(timespec="minutes"))
                else:
                    retries = 0
            except AlreadyRunning:
                logger.warning("Another run holds the lock; skipping this slot")
            except Exception:
                logger.exception("Cycle crashed before finishing; will retry at the next slot")
                await ping("/fail")
        run_now = True

        wake = wake or next_slot(datetime.now(tz))
        logger.info("Next cycle at %s", wake.isoformat(timespec="minutes"))
        while not STOP.is_set() and datetime.now(tz) < wake:
            await asyncio.sleep(min(30, max(1, (wake - datetime.now(tz)).total_seconds())))
    logger.info("Worker stopped")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _install_signal_handlers() -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, STOP.set)


async def _amain(args) -> int:
    _install_signal_handlers()
    if not args.once:
        await serve()
        return 0
    try:
        summary = await run_cycle(
            [c.upper() for c in args.chains] if args.chains else None,
            scrape=not args.no_scrape,
            parse=not args.no_parse,
        )
    except AlreadyRunning:
        logger.error("Another ingest run holds the lock; not starting.")
        return 2
    for note in summary.notes:
        logger.info("note: %s", note)
    print(json.dumps({
        "status": summary.status,
        "chains": {o.chain: ("ok" if o.ok else "problem") for o in summary.outcomes},
    }, ensure_ascii=False))
    return 0 if summary.status == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Supermarket price ingestion worker")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--chains", nargs="*", help="limit to these scraper names (e.g. SHUFERSAL)")
    parser.add_argument("--no-scrape", action="store_true", help="only parse what is already in dumps/")
    parser.add_argument("--no-parse", action="store_true", help="only download")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    sys.exit(main())
