# Isolation, locking and scheduling of the ingestion worker.

import asyncio
import time
from datetime import datetime

import pytest
from sqlalchemy import select

from app import settings, worker
from app.db.models import IngestRun
from app.parser import mass_parser
from app.parser.mass_parser import ChainParseResult
from app.pipeline import runs
from app.pipeline.lock import AlreadyRunning, ingest_lock
from tests.xml_samples import price_name, price_xml, write


@pytest.fixture
def dumps(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DUMPS_DIR", tmp_path)
    monkeypatch.setattr(mass_parser, "DUMPS_ROOT", tmp_path)
    monkeypatch.setattr(settings, "DELETE_AFTER_INGEST", False)
    monkeypatch.setattr(settings, "MIN_FREE_DISK_GB", 0)
    return tmp_path / "Shufersal"


async def test_lock_is_exclusive_and_released():
    async with ingest_lock():
        with pytest.raises(AlreadyRunning):
            async with ingest_lock():
                pass
    async with ingest_lock():   # free again after the first holder left
        pass


async def test_cycle_loads_files_and_records_runs(dumps, session):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    summary = await worker.run_cycle(["SHUFERSAL"], scrape=False)

    assert summary.status == "ok"
    rows = (await session.execute(select(IngestRun.phase, IngestRun.chain, IngestRun.status, IngestRun.rows_applied)
                                  .order_by(IngestRun.id))).all()
    assert ("cycle", None, "ok", 1) in rows and ("parse", "SHUFERSAL", "ok", 1) in rows
    assert await runs.data_age_hours() is not None


async def test_one_failing_chain_does_not_stop_the_others(dumps, monkeypatch, session):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))

    real_parse = worker.parse_chain

    async def flaky(chain):
        if chain == "RAMI_LEVY":
            raise RuntimeError("boom")
        return await real_parse(chain)

    monkeypatch.setattr(worker, "parse_chain", flaky)
    summary = await worker.run_cycle(["RAMI_LEVY", "SHUFERSAL"], scrape=False)

    by_chain = {o.chain: o for o in summary.outcomes}
    assert not by_chain["RAMI_LEVY"].ok and "boom" in by_chain["RAMI_LEVY"].parse_error
    assert by_chain["SHUFERSAL"].ok and by_chain["SHUFERSAL"].parse.files_ok == 1
    assert summary.status == "partial"
    cycle = (await session.execute(select(IngestRun).where(IngestRun.phase == "cycle"))).scalar_one()
    assert cycle.status == "partial" and "RAMI_LEVY" in cycle.error


async def test_failed_scrape_still_parses_what_is_on_disk(dumps, monkeypatch):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))

    async def dead(chain, force_full):
        return False, "ftp down"

    monkeypatch.setattr(worker, "scrape_in_subprocess", dead)
    summary = await worker.run_cycle(["SHUFERSAL"], scrape=True)
    outcome = summary.outcomes[0]
    assert outcome.scrape_ok is False and outcome.parse.files_ok == 1
    assert summary.status == "partial"          # data arrived, but not everything is healthy


async def test_hung_scraper_is_killed_after_timeout(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(settings, "SCRAPE_ATTEMPTS", 1)
    monkeypatch.setattr(worker, "_scrape_command", lambda chain, full: ["sleep", "30"])
    started = time.time()
    ok, error = await worker.scrape_in_subprocess("SHUFERSAL", False)
    assert not ok and "timed out" in error
    assert time.time() - started < 10


async def test_failing_scraper_is_retried(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_ATTEMPTS", 2)
    calls = []
    monkeypatch.setattr(worker, "_scrape_command", lambda chain, full: calls.append(1) or ["false"])
    real_sleep = asyncio.sleep
    monkeypatch.setattr(worker.asyncio, "sleep", lambda s: real_sleep(0))
    ok, error = await worker.scrape_in_subprocess("SHUFERSAL", False)
    assert not ok and len(calls) == 2 and "exit 1" in error


async def test_low_disk_blocks_downloads_but_not_loading(dumps, monkeypatch):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    monkeypatch.setattr(worker, "_disk_ok", lambda: False)
    called = []
    monkeypatch.setattr(worker, "scrape_in_subprocess", lambda *a: called.append(a))
    summary = await worker.run_cycle(["SHUFERSAL"], scrape=True)
    assert not called
    assert summary.outcomes[0].parse.files_ok == 1      # backlog still drains, freeing disk
    assert summary.status != "ok"


async def test_second_cycle_while_one_runs_is_refused(dumps):
    async with ingest_lock():
        with pytest.raises(AlreadyRunning):
            await worker.run_cycle(["SHUFERSAL"], scrape=False)


async def test_abandoned_runs_are_closed_on_next_cycle(dumps, session):
    session.add(IngestRun(phase="cycle", status="running"))
    await session.commit()
    await worker.run_cycle([], scrape=False)
    statuses = (await session.execute(select(IngestRun.status).order_by(IngestRun.id))).scalars().all()
    assert statuses[0] == "failed"


def test_next_slot_lands_on_the_next_boundary(monkeypatch):
    monkeypatch.setattr(settings, "DELTA_EVERY_HOURS", 3)
    assert worker.next_slot(datetime(2026, 5, 12, 10, 20)) == datetime(2026, 5, 12, 12, 0)
    assert worker.next_slot(datetime(2026, 5, 12, 12, 0)) == datetime(2026, 5, 12, 15, 0)
    assert worker.next_slot(datetime(2026, 5, 12, 23, 59)) == datetime(2026, 5, 13, 0, 0)


def test_unknown_chain_names_are_dropped_with_a_note():
    chains, notes = worker.resolve_chains(["SHUFERSAL", "NOT_A_CHAIN"], scrape=True)
    assert chains == ["SHUFERSAL"] and any("NOT_A_CHAIN" in n for n in notes)
