# main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router

# Create the FastAPI app instance
app = FastAPI(
    title="Israeli Supermarket Price Comparison API",
    description="Compare prices across Israeli supermarket chains",
    version="1.0.0",
)

# CORS middleware allows your frontend (running on a different
# port or domain) to call this API.
# Without this, browsers block cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register our routes
app.include_router(router)


@app.get("/")
async def root():
    return {
        "message": "Israeli Supermarket Price API",
        "docs": "/docs",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Task management endpoints ────────────────────────────────────────────────

@app.post("/api/v1/tasks/scrape")
async def trigger_scrape(chains: list[str] | None = None, skip_blocked: bool = True):
    from app.tasks import scrape_all
    task = scrape_all.delay(chains=chains, skip_blocked=skip_blocked)
    return {"task_id": task.id, "status": "queued"}


@app.post("/api/v1/tasks/parse")
async def trigger_parse(chains: list[str] | None = None):
    from app.tasks import parse_all
    task = parse_all.delay(chains=chains)
    return {"task_id": task.id, "status": "queued"}


@app.post("/api/v1/tasks/scrape-and-parse")
async def trigger_pipeline(chains: list[str] | None = None, skip_blocked: bool = True):
    from app.tasks import scrape_and_parse
    task = scrape_and_parse.delay(chains=chains, skip_blocked=skip_blocked)
    return {"task_id": task.id, "status": "queued"}


@app.get("/api/v1/tasks/{task_id}")
async def get_task_status(task_id: str):
    from app.celery_app import app as celery_app
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }