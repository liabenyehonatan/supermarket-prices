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