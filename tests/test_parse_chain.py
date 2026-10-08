# End-to-end behaviour of parse_chain on real parser + real database,
# using tiny synthetic Shufersal-format files in a temporary dumps/ folder.

from decimal import Decimal

import pytest
from sqlalchemy import select

from app import settings
from app.db.models import IngestedFile, Price, Product, Store
from app.parser import mass_parser
from app.parser.mass_parser import parse_chain
from tests.xml_samples import STORES_NAME, price_name, price_xml, stores_xml, write


def seed_status(root, file_names):
    """Create dumps/status/shufersal.json the way the scraper library writes it."""
    import json
    status_dir = root / "status"
    status_dir.mkdir(exist_ok=True)
    path = status_dir / "shufersal.json"
    data = {"events": [], "verified_downloads": [
        {"file_name": n, "system_timestamp": "2026-10-08 10:00:00+03:00", "task_id": "t"} for n in file_names]}
    path.write_text(json.dumps(data))


def status_has(root, file_name):
    import json
    data = json.loads((root / "status" / "shufersal.json").read_text())
    return any(d["file_name"] == file_name for d in data["verified_downloads"])


@pytest.fixture
def dumps(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DUMPS_DIR", tmp_path)
    monkeypatch.setattr(mass_parser, "DUMPS_ROOT", tmp_path)
    monkeypatch.setattr(settings, "DELETE_AFTER_INGEST", False)
    return tmp_path / "Shufersal"


async def current_prices(session):
    rows = await session.execute(
        select(Product.barcode, Price.price)
        .join(Product, Price.product_id == Product.id)
        .where(Price.is_current.is_(True))
        .order_by(Product.barcode)
    )
    return {b: p for b, p in rows.all()}


async def ledger(session):
    rows = await session.execute(select(IngestedFile.file_name, IngestedFile.status, IngestedFile.attempts))
    return {n: (s, a) for n, s, a in rows.all()}


async def test_loads_stores_and_prices_and_records_ledger(dumps, session):
    write(dumps, STORES_NAME, stores_xml([("777", "סניף בדיקה", "חיפה")]))
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [
        ("111", "5.50", "2026-05-12 01:00"), ("222", "3.30", "2026-05-12 01:00")]))

    result = await parse_chain("SHUFERSAL")

    assert result.status == "ok" and result.files_ok == 2 and result.rows_applied > 0
    assert await current_prices(session) == {"111": Decimal("5.50"), "222": Decimal("3.30")}
    store = (await session.execute(select(Store))).scalar_one()
    assert (store.store_id, store.city) == ("777", "חיפה")
    assert set((await ledger(session)).values()) == {("done", 1)}


async def test_second_run_does_not_reload_files(dumps, session):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    await parse_chain("SHUFERSAL")
    second = await parse_chain("SHUFERSAL")
    assert second.files_ok == 0 and second.files_skipped == 1
    assert (await ledger(session))[price_name("777", "20260512-030442")] == ("done", 1)


async def test_file_is_deleted_only_after_load_and_never_reparsed(dumps, session, monkeypatch):
    monkeypatch.setattr(settings, "DELETE_AFTER_INGEST", True)
    path = write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    await parse_chain("SHUFERSAL")
    assert not path.exists()
    assert await current_prices(session) == {"111": Decimal("5.50")}
    again = await parse_chain("SHUFERSAL")      # nothing on disk, nothing to do, nothing breaks
    assert again.files_ok == 0 and again.status == "ok"


async def test_leftover_file_from_a_crash_is_cleaned_without_reparsing(dumps, session, monkeypatch):
    # Simulates: committed + ledger written, process died before unlink().
    name = price_name("777", "20260512-030442")
    write(dumps, name, price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    await parse_chain("SHUFERSAL")
    monkeypatch.setattr(settings, "DELETE_AFTER_INGEST", True)
    await parse_chain("SHUFERSAL")
    assert not (dumps / name).exists()
    assert (await ledger(session))[name] == ("done", 1)   # not parsed a second time


async def test_files_are_applied_oldest_first_even_if_disk_order_differs(dumps, session, monkeypatch):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "9.00", "2026-05-12 03:00")]))
    write(dumps, price_name("777", "20260511-030442"), price_xml("777", [("111", "5.00", "2026-05-11 03:00")]))
    real = mass_parser._dump_files_in
    monkeypatch.setattr(mass_parser, "_dump_files_in", lambda folder: list(reversed(real(folder))))
    await parse_chain("SHUFERSAL")
    assert await current_prices(session) == {"111": Decimal("9.00")}
    history = (await session.execute(select(Price.price, Price.is_current).order_by(Price.id))).all()
    assert history == [(Decimal("5.00"), False), (Decimal("9.00"), True)]


async def test_truncated_file_is_rejected_not_half_loaded(dumps, session):
    seed_status(dumps.parent, [price_name("777", "20260512-030442"), price_name("777", "20260511-030442")])
    good = price_xml("777", [(f"{i}", "5.00", "2026-05-12 01:00") for i in range(20)])
    write(dumps, price_name("777", "20260511-030442"), good)
    await parse_chain("SHUFERSAL")
    cut = good[: len(good) // 2]                       # download cut off mid-item
    write(dumps, price_name("777", "20260512-030442"), cut)

    result = await parse_chain("SHUFERSAL")

    assert result.files_failed == 1 and result.files_ok == 0
    assert len(await current_prices(session)) == 20   # nothing was closed or changed
    assert (await ledger(session))[price_name("777", "20260512-030442")][0] == "failed"
    # the damaged copy is dropped and the scraper is told to fetch it again
    assert not (dumps / price_name("777", "20260512-030442")).exists()
    assert not status_has(dumps.parent, price_name("777", "20260512-030442"))


async def test_poison_file_is_quarantined_after_max_attempts_and_others_still_load(dumps, session, monkeypatch):
    monkeypatch.setattr(settings, "PARSE_MAX_ATTEMPTS", 3)
    bad_name = price_name("777", "20260512-030442")
    seed_status(dumps.parent, [bad_name])
    write(dumps, price_name("778", "20260512-030442"), price_xml("778", [("555", "2.00", "2026-05-12 01:00")]))

    # Each cycle the scraper would fetch the broken file again; simulate that.
    write(dumps, bad_name, "<<<not xml")
    first = await parse_chain("SHUFERSAL")
    assert first.files_ok == 1 and first.files_failed == 1       # the good file was not blocked
    assert not status_has(dumps.parent, bad_name)                # first failures: ask for a refetch

    seed_status(dumps.parent, [bad_name])
    write(dumps, bad_name, "<<<not xml")
    await parse_chain("SHUFERSAL")

    seed_status(dumps.parent, [bad_name])
    write(dumps, bad_name, "<<<not xml")
    third = await parse_chain("SHUFERSAL")

    assert third.files_quarantined == 1
    assert not (dumps / bad_name).exists()
    assert (settings.DUMPS_DIR / "_quarantine" / "Shufersal" / bad_name).exists()
    assert status_has(dumps.parent, bad_name)                    # now the scraper must NOT refetch it
    assert (await ledger(session))[bad_name][0] == "quarantined"

    write(dumps, bad_name, "<<<not xml")                         # a fourth delivery is ignored quietly
    fourth = await parse_chain("SHUFERSAL")
    assert fourth.files_failed == 0 and not (dumps / bad_name).exists()


async def test_real_file_with_zero_items_fails_instead_of_recording_success(dumps, session):
    empty_but_big = price_xml("777", []).replace("</root>", "<!--" + "x" * 3000 + "--></root>")
    write(dumps, price_name("777", "20260512-030442"), empty_but_big)
    result = await parse_chain("SHUFERSAL")
    assert result.files_failed == 1 and result.files_ok == 0


def test_file_timestamp_formats():
    from datetime import datetime

    from app.parser.ledger import file_timestamp

    assert file_timestamp("PriceFull7290027600007-001-001-20260512-030442.xml") == datetime(2026, 5, 12, 3, 4, 42)
    assert file_timestamp("Stores7290027600007-000-202605120201.xml") == datetime(2026, 5, 12, 2, 1, 0)
    assert file_timestamp("garbage.xml") is None
