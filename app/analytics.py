# app/analytics.py
#
# The site's own visitor statistics. The browser sends anonymous events (lib/track.ts in the frontend); the /stats page
# reads the summary with a password. Stored: a random id the browser made, what was done and on which page, the kind of
# device. Not stored: IP addresses, raw browser strings, names of any kind.

import hmac
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Literal, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.database import get_db
from app.db.models import SiteEvent

router = APIRouter(prefix="/api/v1", include_in_schema=False)

TZ = "Asia/Jerusalem"
MIN_PASSWORD_LENGTH = 12

# Doing one of these is what makes a visitor a "real user": they used the site, they did not only land on it.
ACTION_EVENTS = ("search", "product_open", "basket_add", "basket_compare", "scan", "deal_open")
_ACTIONS_SQL = "(" + ",".join(f"'{e}'" for e in ACTION_EVENTS) + ")"
# The first funnel step after arriving: anything that shows interest in a product.
_EXPLORE_SQL = "('search','product_open','scan','deal_open')"
_PAGE_SQL = "CASE WHEN path LIKE '/product/%' THEN '/product/*' ELSE COALESCE(path, '') END"
_DAY_SQL = f"(created_at AT TIME ZONE '{TZ}')"

_BOT = re.compile(
    r"bot\b|bot/|crawl|spider|slurp|headless|lighthouse|pagespeed|preview|facebookexternalhit|whatsapp|telegram"
    r"|python|curl|wget|httpx|okhttp|node-fetch|go-http|axios|java/|uptime|monitor|healthcheck",
    re.I,
)
_SOURCE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


def is_bot(user_agent: str) -> bool:
    return not user_agent or bool(_BOT.search(user_agent))


def describe_device(user_agent: str) -> tuple[str, str, str]:
    """(device, os, browser) in broad categories: all that is kept of the browser string."""
    ua = user_agent
    if "iPad" in ua or ("Android" in ua and "Mobile" not in ua):
        device = "tablet"
    elif "Mobi" in ua or "iPhone" in ua or "Android" in ua:
        device = "mobile"
    else:
        device = "desktop"

    if "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Android" in ua:
        os_name = "Android"
    elif "Windows" in ua:
        os_name = "Windows"
    elif "Mac OS" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = "other"

    if "SamsungBrowser" in ua:
        browser = "Samsung"
    elif "Edg" in ua:
        browser = "Edge"
    elif "OPR/" in ua:
        browser = "Opera"
    elif "Firefox" in ua or "FxiOS" in ua:
        browser = "Firefox"
    elif "Chrome" in ua or "CriOS" in ua:
        browser = "Chrome"
    elif "Safari" in ua:
        browser = "Safari"
    else:
        browser = "other"
    return device, os_name, browser


# ── Collecting ───────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    event: Literal["page_view", "click", "time", *ACTION_EVENTS]
    path: Optional[str] = None
    label: Optional[str] = None
    value: Optional[int] = Field(default=None, ge=0, le=1_000_000)

    @field_validator("path")
    @classmethod
    def _clean_path(cls, v: Optional[str]) -> Optional[str]:
        if not v or not v.startswith("/"):
            return None
        return re.split(r"[?#]", v, maxsplit=1)[0][:200]

    @field_validator("label")
    @classmethod
    def _clean_label(cls, v: Optional[str]) -> Optional[str]:
        v = " ".join(v.split())[:80] if v else None
        return v or None


class CollectIn(BaseModel):
    visitor_id: UUID
    session_id: UUID
    source: Optional[str] = None
    events: List[EventIn] = Field(min_length=1, max_length=50)

    @field_validator("source")
    @classmethod
    def _clean_source(cls, v: Optional[str]) -> Optional[str]:
        v = v.strip().lower() if v else None
        return v if v and _SOURCE.match(v) else None


@router.post("/events", status_code=204)
async def collect(body: CollectIn, request: Request, db: AsyncSession = Depends(get_db)):
    user_agent = request.headers.get("user-agent", "")
    if not is_bot(user_agent):
        device, os_name, browser = describe_device(user_agent)
        await db.execute(insert(SiteEvent), [
            {"visitor_id": body.visitor_id, "session_id": body.session_id, "source": body.source, "event": e.event,
             "path": e.path, "label": e.label, "value": e.value, "device": device, "os": os_name, "browser": browser}
            for e in body.events
        ])
        await db.commit()
    return Response(status_code=204)


# ── Reading ──────────────────────────────────────────────────────────────────

class SummaryIn(BaseModel):
    password: str = Field(max_length=200)
    days: int = Field(default=30, ge=1, le=366)


def _check_password(given: str) -> None:
    configured = settings.STATS_PASSWORD
    if len(configured) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=503, detail="stats password not configured")
    if not hmac.compare_digest(given.encode(), configured.encode()):
        raise HTTPException(status_code=401, detail="wrong password")


_TOTALS_SQL = f"""
    SELECT count(DISTINCT visitor_id) AS visitors,
           count(DISTINCT visitor_id) FILTER (WHERE event IN {_ACTIONS_SQL}) AS real_users,
           count(DISTINCT session_id) AS sessions,
           count(*) FILTER (WHERE event = 'page_view') AS page_views,
           count(*) FILTER (WHERE event IN {_ACTIONS_SQL}) AS actions,
           COALESCE(sum(value) FILTER (WHERE event = 'time'), 0) AS seconds,
           count(DISTINCT session_id) FILTER (WHERE event = 'time') AS timed_sessions
      FROM site_events
     WHERE created_at >= :start AND created_at < :end
"""


async def _rows(db: AsyncSession, sql: str, **params) -> list[dict]:
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


@router.post("/stats/summary")
async def stats_summary(body: SummaryIn, db: AsyncSession = Depends(get_db)):
    """A POST on purpose: the edge nginx caches GET answers under /api/ for everyone."""
    _check_password(body.password)

    now = datetime.now(ZoneInfo(TZ))
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = midnight - timedelta(days=body.days - 1)
    prev_start = start - timedelta(days=body.days)
    window = {"start": start}

    totals = (await _rows(db, _TOTALS_SQL, start=start, end=now + timedelta(minutes=1)))[0]
    previous = (await _rows(db, _TOTALS_SQL, start=prev_start, end=start))[0]

    new_old = (await _rows(db, """
        SELECT count(*) FILTER (WHERE first_seen >= :start) AS new_visitors,
               count(*) FILTER (WHERE first_seen <  :start) AS returning_visitors
          FROM (SELECT visitor_id, min(created_at) AS first_seen
                  FROM site_events
                 WHERE visitor_id IN (SELECT DISTINCT visitor_id FROM site_events WHERE created_at >= :start)
                 GROUP BY visitor_id) v
    """, **window))[0]

    by_day = await _rows(db, f"""
        SELECT {_DAY_SQL}::date AS day,
               count(DISTINCT visitor_id) AS visitors,
               count(DISTINCT visitor_id) FILTER (WHERE event IN {_ACTIONS_SQL}) AS real_users,
               count(DISTINCT session_id) AS sessions,
               count(*) FILTER (WHERE event = 'page_view') AS page_views
          FROM site_events WHERE created_at >= :start GROUP BY 1
    """, **window)
    day_map = {r["day"]: r for r in by_day}
    daily = []
    for n in range(body.days):
        day = (start + timedelta(days=n)).date()
        row = day_map.get(day, {"visitors": 0, "real_users": 0, "sessions": 0, "page_views": 0})
        daily.append({**row, "day": day.isoformat()})

    hours = {int(r["n"]): r["visitors"] for r in await _rows(db, f"""
        SELECT extract(hour FROM {_DAY_SQL}) AS n, count(DISTINCT visitor_id) AS visitors
          FROM site_events WHERE created_at >= :start GROUP BY 1
    """, **window)}
    weekdays = {int(r["n"]): r["visitors"] for r in await _rows(db, f"""
        SELECT extract(dow FROM {_DAY_SQL}) AS n, count(DISTINCT visitor_id) AS visitors
          FROM site_events WHERE created_at >= :start GROUP BY 1
    """, **window)}

    funnel_row = (await _rows(db, f"""
        SELECT count(DISTINCT visitor_id) AS visit,
               count(DISTINCT visitor_id) FILTER (WHERE event IN {_EXPLORE_SQL}) AS explore,
               count(DISTINCT visitor_id) FILTER (WHERE event = 'basket_add') AS basket_add,
               count(DISTINCT visitor_id) FILTER (WHERE event = 'basket_compare') AS basket_compare
          FROM site_events WHERE created_at >= :start
    """, **window))[0]

    frequency_counts: dict[str, int] = defaultdict(int)
    for r in await _rows(db, f"""
        SELECT count(DISTINCT {_DAY_SQL}::date) AS days FROM site_events
         WHERE created_at >= :start GROUP BY visitor_id
    """, **window):
        d = r["days"]
        frequency_counts["1" if d == 1 else "2-3" if d <= 3 else "4-7" if d <= 7 else "8+"] += 1

    visitors = await _rows(db, f"""
        SELECT visitor_id, min(created_at) AS first_seen, max(created_at) AS last_seen,
               count(DISTINCT {_DAY_SQL}::date) AS days_active,
               count(DISTINCT session_id) AS sessions,
               count(*) FILTER (WHERE event = 'page_view') AS page_views,
               count(*) FILTER (WHERE event IN {_ACTIONS_SQL}) AS actions,
               COALESCE(sum(value) FILTER (WHERE event = 'time'), 0) AS seconds,
               max(device) AS device, max(source) AS source
          FROM site_events WHERE created_at >= :start
         GROUP BY visitor_id
         ORDER BY actions DESC, seconds DESC, last_seen DESC
         LIMIT 100
    """, **window)
    for v in visitors:
        v["id"] = str(v.pop("visitor_id"))[:6]   # enough to tell people apart in the table

    async def by_visitor(column: str) -> list[dict]:
        return await _rows(db, f"""
            SELECT {column} AS name, count(DISTINCT visitor_id) AS visitors
              FROM site_events WHERE created_at >= :start GROUP BY 1 ORDER BY 2 DESC
        """, **window)

    async def products(condition: str, barcode: str) -> list[dict]:
        return await _rows(db, f"""
            SELECT e.barcode, p.name, count(*) AS views, count(DISTINCT e.visitor_id) AS visitors
              FROM (SELECT {barcode} AS barcode, visitor_id FROM site_events
                     WHERE created_at >= :start AND {condition}) e
              LEFT JOIN products p ON p.barcode = e.barcode
             GROUP BY e.barcode, p.name
             ORDER BY views DESC, e.barcode
             LIMIT 15
        """, **window)

    data = {
        "period": {"days": body.days, "from": start.date().isoformat()},
        "collecting_since": (await db.execute(text("SELECT min(created_at) FROM site_events"))).scalar(),
        "live_now": (await db.execute(text(
            "SELECT count(DISTINCT visitor_id) FROM site_events WHERE created_at > now() - interval '5 minutes'"
        ))).scalar(),
        "kpis": {
            "visitors": totals["visitors"],
            "real_users": totals["real_users"],
            "sessions": totals["sessions"],
            "page_views": totals["page_views"],
            "actions": totals["actions"],
            "avg_session_seconds": round(totals["seconds"] / totals["timed_sessions"]) if totals["timed_sessions"] else 0,
            "actions_per_real_user": round(totals["actions"] / totals["real_users"], 1) if totals["real_users"] else 0,
            **new_old,
            "previous": {k: previous[k] for k in ("visitors", "real_users", "sessions", "page_views", "actions")},
        },
        "daily": daily,
        "hours": [{"hour": h, "visitors": hours.get(h, 0)} for h in range(24)],
        "weekdays": [{"day": d, "visitors": weekdays.get(d, 0)} for d in range(7)],
        "funnel": [{"step": step, "visitors": funnel_row[step]}
                   for step in ("visit", "explore", "basket_add", "basket_compare")],
        "frequency": [{"bucket": b, "visitors": frequency_counts.get(b, 0)} for b in ("1", "2-3", "4-7", "8+")],
        "actions": await _rows(db, f"""
            SELECT event, count(*) AS count, count(DISTINCT visitor_id) AS visitors
              FROM site_events WHERE created_at >= :start AND event IN {_ACTIONS_SQL}
             GROUP BY event ORDER BY count DESC
        """, **window),
        "clicks": await _rows(db, f"""
            SELECT label, {_PAGE_SQL} AS page, count(*) AS clicks, count(DISTINCT visitor_id) AS visitors
              FROM site_events WHERE created_at >= :start AND event = 'click' AND label IS NOT NULL
             GROUP BY 1, 2 ORDER BY clicks DESC, label LIMIT 40
        """, **window),
        "pages": await _rows(db, f"""
            SELECT {_PAGE_SQL} AS page, count(*) AS views, count(DISTINCT visitor_id) AS visitors
              FROM site_events WHERE created_at >= :start AND event = 'page_view'
             GROUP BY 1 ORDER BY views DESC LIMIT 20
        """, **window),
        "searches": await _rows(db, """
            SELECT label AS term, count(*) AS count, count(DISTINCT visitor_id) AS visitors,
                   round(avg(value))::int AS results
              FROM site_events WHERE created_at >= :start AND event = 'search' AND label IS NOT NULL
             GROUP BY label ORDER BY count DESC, label LIMIT 30
        """, **window),
        "searches_empty": await _rows(db, """
            SELECT label AS term, count(*) AS count, count(DISTINCT visitor_id) AS visitors
              FROM site_events WHERE created_at >= :start AND event = 'search' AND value = 0 AND label IS NOT NULL
             GROUP BY label ORDER BY count DESC, label LIMIT 20
        """, **window),
        "products_viewed": await products("event = 'page_view' AND path LIKE '/product/%'", "substr(path, 10)"),
        "products_added": await products("event = 'basket_add' AND label IS NOT NULL", "label"),
        "sources": await _rows(db, """
            SELECT COALESCE(source, 'direct') AS name, count(*) AS sessions, count(DISTINCT visitor_id) AS visitors
              FROM (SELECT session_id, visitor_id, max(source) AS source FROM site_events
                     WHERE created_at >= :start GROUP BY session_id, visitor_id) s
             GROUP BY 1 ORDER BY sessions DESC LIMIT 15
        """, **window),
        "devices": await by_visitor("device"),
        "systems": await by_visitor("os"),
        "browsers": await by_visitor("browser"),
        "visitors": visitors,
    }
    return JSONResponse(jsonable_encoder(data), headers={"Cache-Control": "no-store"})
