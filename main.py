# main.py

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, TimeoutError as PoolTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.api.routes import router
from app.seo import router as seo_router
from app.db.database import get_db

# Create the FastAPI app instance
app = FastAPI(
    title="Israeli Supermarket Price Comparison API",
    description="Compare prices across Israeli supermarket chains",
    version="1.0.0",
)

# CORS lets a browser on another origin call this API. Behind the bundled nginx
# the frontend and API share an origin and none of this is exercised; it matters
# when the frontend is hosted elsewhere (set FRONTEND_URL, comma-separated).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.FRONTEND_URLS or settings.DEV_CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Register our routes
app.include_router(router)
app.include_router(seo_router)   # page heads for search engines, robots.txt, sitemaps


@app.exception_handler(DBAPIError)
@app.exception_handler(PoolTimeoutError)
async def database_busy(request: Request, exc: Exception):
    """The database took too long (a statement over its time limit, or no connection free): the same answer for
    every such case, a "busy, try again" 503, instead of a stack trace and a 500. The page asks again a moment later."""
    logging.getLogger(__name__).warning("database busy on %s %s: %s", request.method, request.url.path, str(exc)[:120])
    return JSONResponse({"detail": "The service is busy, try again in a moment."}, status_code=503, headers={"Retry-After": "5"})


@app.get("/")
async def root():
    return {
        "message": "Israeli Supermarket Price API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """Liveness + database reachability. 503 when the database does not answer."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "degraded", "db": False}, status_code=503)
    return {"status": "ok", "db": True}


@app.get("/health/data")
async def health_data():
    """
    Data freshness for an uptime monitor: 503 when the last successful ingest
    cycle is older than MAX_DATA_AGE_HOURS (or there never was one). Kept apart
    from /health so stale data never makes a container orchestrator restart a
    perfectly healthy API.
    """
    from app.pipeline.runs import data_age_hours

    try:
        age = await data_age_hours()
    except Exception:
        return JSONResponse({"status": "degraded", "db": False}, status_code=503)
    fresh = age is not None and age <= settings.MAX_DATA_AGE_HOURS
    import asyncio
    import logging

    from app.pipeline.watchdog import stale_chains

    checked = True
    try:
        stale = [name for name, _ in await asyncio.wait_for(stale_chains(), timeout=3)]
    except Exception as exc:       # the chain check must never take the freshness answer down with it
        logging.getLogger(__name__).warning("stale-chain check failed: %s", exc)
        stale, checked = [], False
    healthy = fresh and not stale
    return JSONResponse(
        {
            "status": "ok" if healthy else ("stale" if not fresh else "chains_stale"),
            "data_age_hours": None if age is None else round(age, 1),
            "max_age_hours": settings.MAX_DATA_AGE_HOURS,
            "stale_chains": stale,
            "stale_chains_checked": checked,
        },
        status_code=200 if healthy else 503,
    )
