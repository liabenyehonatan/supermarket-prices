# Silent-failure detection: stale chains, files left on disk, and /health/data.

from datetime import datetime, timedelta

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import func

from app import settings
from app.db.models import Chain, IngestRun, Store
from app.pipeline import watchdog
from main import app


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _chains(session):
    fresh = Chain(chain_id="1", name="חיה")
    dead = Chain(chain_id="2", name="מתה")
    never = Chain(chain_id="3", name="לא נטענה")
    empty = Chain(chain_id="4", name="בלי חנויות")                 # e.g. a chain we skip on purpose: not an alarm
    session.add_all([fresh, dead, never, empty])
    await session.flush()
    now = datetime.utcnow()
    session.add_all([
        Store(chain_id=fresh.id, store_id="1", last_full_at=now - timedelta(hours=5)),
        Store(chain_id=dead.id, store_id="1", last_full_at=now - timedelta(days=9)),
        Store(chain_id=dead.id, store_id="2", last_full_at=now - timedelta(days=10)),
        Store(chain_id=never.id, store_id="1"),
    ])
    await session.commit()


async def test_stale_chains_lists_dead_and_never_loaded_chains(session):
    await _chains(session)
    names = {name: newest for name, newest in await watchdog.stale_chains(days=4)}
    assert set(names) == {"מתה", "לא נטענה"}
    assert names["לא נטענה"] is None


def test_leftover_files_ignores_status_quarantine_and_json(tmp_path):
    (tmp_path / "status").mkdir()
    (tmp_path / "status" / "a.json").write_text("{}")
    (tmp_path / "_quarantine").mkdir()
    (tmp_path / "_quarantine" / "bad.xml").write_text("x")
    (tmp_path / "Bareket").mkdir()
    (tmp_path / "Bareket" / "PriceFull123").write_bytes(b"\x1f\x8b")        # downloaded, never loaded
    (tmp_path / "Bareket" / "PriceFull124.xml").write_text("<x/>")
    (tmp_path / "Clean").mkdir()
    assert watchdog.leftover_files(tmp_path) == {"Bareket": 2}


async def test_check_and_alert_reports_problems_and_pings(session, tmp_path, monkeypatch):
    await _chains(session)
    (tmp_path / "Bareket").mkdir()
    (tmp_path / "Bareket" / "PriceFull1").write_bytes(b"x")
    sent = []

    async def fake_post(self, url, content=None, **kw):
        sent.append((url, content.decode()))
        return httpx.Response(200)

    monkeypatch.setattr(settings, "HEALTHCHECK_CHAINS_URL", "https://hc.example/abc")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    problems = await watchdog.check_and_alert(tmp_path)
    assert any("מתה" in p for p in problems) and any("Bareket" in p for p in problems)
    assert sent[0][0] == "https://hc.example/abc/fail" and "מתה" in sent[0][1]


async def test_health_data_goes_503_when_a_chain_is_stale(client, session):
    session.add(IngestRun(phase="cycle", status="ok", finished_at=func.now()))
    await _chains(session)
    r = await client.get("/health/data")
    assert r.status_code == 503
    assert r.json()["status"] == "chains_stale" and set(r.json()["stale_chains"]) == {"מתה", "לא נטענה"}


async def test_clean_run_sends_a_success_ping(session, tmp_path, monkeypatch):
    fresh = Chain(chain_id="1", name="חיה")
    session.add(fresh)
    await session.flush()
    session.add(Store(chain_id=fresh.id, store_id="1", last_full_at=datetime.utcnow()))
    await session.commit()
    sent = []

    async def fake_post(self, url, content=None, **kw):
        sent.append(url)
        return httpx.Response(200)

    monkeypatch.setattr(settings, "HEALTHCHECK_CHAINS_URL", "https://hc.example/abc")
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await watchdog.check_and_alert(tmp_path) == []
    assert sent == ["https://hc.example/abc"]


async def test_health_data_survives_a_failing_chain_check(client, session, monkeypatch):
    session.add(IngestRun(phase="cycle", status="ok", finished_at=func.now()))
    await session.commit()

    async def boom(*a, **k):
        raise RuntimeError("db slow")

    monkeypatch.setattr(watchdog, "stale_chains", boom)
    r = await client.get("/health/data")
    assert r.status_code == 200 and r.json()["stale_chains_checked"] is False
