# The site's own visitor statistics: what is collected, what is refused, and who may read it.

from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from app import settings
from main import app

PASSWORD = "a-long-enough-password"
PHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1"
DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


@pytest.fixture
async def client():
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def stats_on(monkeypatch):
    monkeypatch.setattr(settings, "STATS_PASSWORD", PASSWORD)


async def send(client, events, *, visitor=None, session=None, ua=PHONE_UA, source=None):
    return await client.post(
        "/api/v1/events",
        json={"visitor_id": str(visitor or uuid4()), "session_id": str(session or uuid4()), "source": source,
              "events": events},
        headers={"User-Agent": ua},
    )


async def stored(session):
    from app.db.models import SiteEvent

    return (await session.execute(select(SiteEvent).order_by(SiteEvent.id))).scalars().all()


async def summary(client, days=30, password=PASSWORD):
    r = await client.post("/api/v1/stats/summary", json={"password": password, "days": days})
    assert r.status_code == 200, r.text
    return r.json()


# ── collecting ───────────────────────────────────────────────────────────────

async def test_events_are_stored_with_the_device_but_no_address_or_raw_browser_string(client, session):
    r = await send(client, [{"event": "page_view", "path": "/basket"}], source="google.com")
    assert r.status_code == 204
    [row] = await stored(session)
    assert (row.event, row.path, row.device, row.os, row.browser, row.source) == (
        "page_view", "/basket", "mobile", "iOS", "Safari", "google.com")
    columns = set(row.__table__.columns.keys())
    assert not columns & {"ip", "ip_address", "user_agent", "ua"}


async def test_crawlers_are_not_counted(client, session):
    r = await send(client, [{"event": "page_view", "path": "/"}], ua="Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert r.status_code == 204
    assert await stored(session) == []


async def test_unknown_event_names_are_refused(client, session):
    assert (await send(client, [{"event": "drop_tables"}])).status_code == 422
    assert await stored(session) == []


async def test_a_batch_has_a_size_limit(client):
    assert (await send(client, [{"event": "click", "label": "x"}] * 51)).status_code == 422


async def test_long_text_is_cut_and_a_query_string_is_removed_from_the_path(client, session):
    await send(client, [{"event": "click", "path": "/?q=secret", "label": "א" * 500}])
    [row] = await stored(session)
    assert row.path == "/"
    assert len(row.label) == 80


async def test_a_malformed_source_is_dropped(client, session):
    await send(client, [{"event": "page_view", "path": "/"}], source="<script>alert(1)</script>")
    [row] = await stored(session)
    assert row.source is None


# ── reading ──────────────────────────────────────────────────────────────────

async def test_a_wrong_password_gets_nothing(client, stats_on):
    r = await client.post("/api/v1/stats/summary", json={"password": "wrong-password-here", "days": 7})
    assert r.status_code == 401
    assert "visitors" not in r.text


async def test_without_a_configured_password_the_statistics_stay_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "STATS_PASSWORD", "")
    r = await client.post("/api/v1/stats/summary", json={"password": "", "days": 7})
    assert r.status_code == 503


async def test_a_short_configured_password_keeps_the_statistics_closed(client, monkeypatch):
    monkeypatch.setattr(settings, "STATS_PASSWORD", "short")
    r = await client.post("/api/v1/stats/summary", json={"password": "short", "days": 7})
    assert r.status_code == 503


async def test_the_statistics_cannot_be_read_with_get(client, stats_on):
    # the edge nginx caches GET answers under /api/ for every visitor; this answer must never go through that
    assert (await client.get("/api/v1/stats/summary")).status_code == 405


async def test_the_answer_forbids_caching(client, stats_on):
    r = await client.post("/api/v1/stats/summary", json={"password": PASSWORD, "days": 7})
    assert r.headers["cache-control"] == "no-store"


async def test_a_real_user_is_someone_who_did_something(client, session, stats_on):
    looker, doer = uuid4(), uuid4()
    await send(client, [{"event": "page_view", "path": "/"}], visitor=looker)
    await send(client, [{"event": "page_view", "path": "/"},
                        {"event": "search", "path": "/", "label": "חלב", "value": 12}], visitor=doer)
    data = await summary(client)
    assert data["kpis"]["visitors"] == 2
    assert data["kpis"]["real_users"] == 1


async def test_sessions_page_views_and_time_are_summed(client, session, stats_on):
    v, s1, s2 = uuid4(), uuid4(), uuid4()
    await send(client, [{"event": "page_view", "path": "/"}, {"event": "page_view", "path": "/basket"},
                        {"event": "time", "path": "/basket", "value": 100}], visitor=v, session=s1)
    await send(client, [{"event": "page_view", "path": "/"}, {"event": "time", "path": "/", "value": 20}],
               visitor=v, session=s2)
    k = (await summary(client))["kpis"]
    assert (k["visitors"], k["sessions"], k["page_views"]) == (1, 2, 3)
    assert k["avg_session_seconds"] == 60


async def test_clicks_are_ranked_by_button_and_page(client, session, stats_on):
    v = uuid4()
    await send(client, [{"event": "click", "path": "/", "label": "הוספה לסל"},
                        {"event": "click", "path": "/", "label": "הוספה לסל"},
                        {"event": "click", "path": "/basket", "label": "השוואת סל"}], visitor=v)
    clicks = (await summary(client))["clicks"]
    assert clicks[0] == {"label": "הוספה לסל", "page": "/", "clicks": 2, "visitors": 1}
    assert len(clicks) == 2


async def test_product_pages_are_grouped_and_named(client, session, stats_on, store):
    from app.db.models import Product

    session.add(Product(barcode="7290000000017", name="חלב 3%"))
    await session.commit()
    await send(client, [{"event": "page_view", "path": "/product/7290000000017"},
                        {"event": "page_view", "path": "/product/7290000000099"}])
    data = await summary(client)
    assert data["pages"] == [{"page": "/product/*", "views": 2, "visitors": 1}]
    assert {"barcode": "7290000000017", "name": "חלב 3%", "views": 1, "visitors": 1} in data["products_viewed"]


async def test_searches_without_results_are_listed_apart(client, session, stats_on):
    await send(client, [{"event": "search", "label": "חלב", "value": 20},
                        {"event": "search", "label": "קוויאר", "value": 0}])
    data = await summary(client)
    assert {row["term"] for row in data["searches"]} == {"חלב", "קוויאר"}
    assert [row["term"] for row in data["searches_empty"]] == ["קוויאר"]


async def test_the_funnel_only_counts_people_once_per_step(client, session, stats_on):
    v = uuid4()
    await send(client, [{"event": "page_view", "path": "/"}, {"event": "search", "label": "a", "value": 1},
                        {"event": "search", "label": "b", "value": 1}, {"event": "basket_add", "label": "1"}], visitor=v)
    await send(client, [{"event": "page_view", "path": "/"}])
    steps = {s["step"]: s["visitors"] for s in (await summary(client))["funnel"]}
    assert steps == {"visit": 2, "explore": 1, "basket_add": 1, "basket_compare": 0}


async def test_every_day_of_the_period_is_present_even_without_visits(client, session, stats_on):
    await send(client, [{"event": "page_view", "path": "/"}])
    daily = (await summary(client, days=7))["daily"]
    assert len(daily) == 7
    assert daily[-1]["visitors"] == 1
    assert daily[0]["visitors"] == 0


async def test_visitors_are_listed_by_how_much_they_did_without_their_full_id(client, session, stats_on):
    busy, idle = uuid4(), uuid4()
    await send(client, [{"event": "page_view", "path": "/"}], visitor=idle, ua=DESKTOP_UA)
    await send(client, [{"event": "search", "label": "a", "value": 1}, {"event": "basket_add", "label": "1"},
                        {"event": "time", "value": 90}], visitor=busy, source="facebook.com")
    rows = (await summary(client))["visitors"]
    assert rows[0]["actions"] == 2 and rows[0]["seconds"] == 90 and rows[0]["source"] == "facebook.com"
    assert rows[0]["id"] == str(busy)[:6]
    assert rows[1]["device"] == "desktop"


async def test_new_and_returning_visitors(client, session, stats_on):
    from sqlalchemy import update

    from app.db.models import SiteEvent

    old = uuid4()
    await send(client, [{"event": "page_view", "path": "/"}], visitor=old)
    await session.execute(update(SiteEvent).values(created_at=SiteEvent.created_at - __import__("datetime").timedelta(days=60)))
    await session.commit()
    await send(client, [{"event": "page_view", "path": "/"}], visitor=old)
    await send(client, [{"event": "page_view", "path": "/"}])
    k = (await summary(client, days=7))["kpis"]
    assert (k["new_visitors"], k["returning_visitors"]) == (1, 1)


async def test_old_events_are_removed_by_housekeeping(client, session):
    from datetime import timedelta

    from sqlalchemy import update

    from app.db.models import SiteEvent
    from app.pipeline import maintenance

    await send(client, [{"event": "page_view", "path": "/old"}])
    await session.execute(update(SiteEvent).values(created_at=SiteEvent.created_at - timedelta(days=500)))
    await session.commit()
    await send(client, [{"event": "page_view", "path": "/new"}])
    assert await maintenance.prune_site_events(400) == 1
    session.expire_all()
    assert [row.path for row in await stored(session)] == ["/new"]


async def test_the_stats_page_exists_but_is_not_for_search_engines(client, monkeypatch):
    from app import seo

    async def shell():
        return "<html><head><title>x</title></head><body><div id=\"root\"></div></body></html>"

    monkeypatch.setattr(seo, "get_shell", shell)
    r = await client.get("/_seo/stats")
    assert r.status_code == 200
    assert "noindex" in r.text
