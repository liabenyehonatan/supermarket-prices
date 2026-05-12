# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Israeli supermarket price comparison app (Machirista) to premium production quality across security, features, pipeline reliability, and polish.

**Architecture:** Four sequential phases — each phase must fully complete before the next begins. Within each phase, tasks marked **[PARALLEL]** are independent and can be executed concurrently by separate subagents.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL (pg_trgm), Celery + Redis, Next.js 15 App Router, Zustand, Tailwind, framer-motion, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-12-production-hardening-design.md`

---

## File Map

### New files
| Path | Purpose |
|---|---|
| `app/api/auth.py` | `verify_api_key` FastAPI dependency |
| `app/utils/__init__.py` | package marker |
| `app/utils/transfer.py` | `get_transfer_url()` for basket CTA |
| `app/utils/haversine.py` | Haversine distance formula |
| `nginx/nginx.conf` | Reverse proxy config |
| `docs/deployment.md` | VPS deployment guide |
| `tests/__init__.py` | test package marker |
| `tests/conftest.py` | pytest fixtures |
| `tests/test_auth.py` | auth unit tests |
| `tests/test_transfer.py` | transfer URL unit tests |
| `tests/test_haversine.py` | haversine unit tests |
| `tests/test_basket_ranking.py` | basket sort logic tests |
| `frontend/src/lib/share.ts` | basket encode/decode helpers |
| `frontend/src/app/[locale]/admin/page.tsx` | admin dashboard page |

### Modified files
| Path | Changes |
|---|---|
| `requirements.txt` | add pytest, pytest-asyncio, sentry-sdk |
| `main.py` | CORS env var, real health check, auth on task routes |
| `app/api/routes.py` | stats, history, promotions, categories, near-me, fuzzy search, admin |
| `app/api/schemas.py` | PromotionResponse, PriceHistoryPoint, StatsResponse, CategoryCount; update BasketStoreTotal + PriceAtStore |
| `app/tasks.py` | remove `_run_async`, add `geocode_new` task |
| `app/celery_app.py` | `SKIP_BLOCKED_CHAINS` env var, add geocode beat entry |
| `app/geocoder.py` | add `only_missing` param |
| `app/parser/mass_parser.py` | trigger geocode after store parse |
| `docker-compose.yml` | split celery into worker + beat services |
| `.env.example` | document all new env vars |
| `frontend/src/lib/api.ts` | new fetch functions, updated types |
| `frontend/src/lib/basket-store.ts` | savedAt expiry, share helpers |
| `frontend/src/components/basket/BasketResults.tsx` | real transfer URL, coverage divider, freshness |
| `frontend/src/components/basket/BasketBuilder.tsx` | near-me toggle, URL param hydration |
| `frontend/src/components/layout/StatsBar.tsx` | live API data |
| `frontend/src/app/[locale]/product/[barcode]/page.tsx` | sparkline, inline promotions, freshness |
| `frontend/src/app/[locale]/search/page.tsx` | category chip row |

### Deleted files
`frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/` (dir), `frontend/src/styles/global.css`, `frontend/src/vite-env.d.ts`, `frontend/src/api/client.ts`

---

## Phase 1 — Critical Fixes

> Tasks 1.1, 1.2, and 1.5 are **[PARALLEL]** — they touch different files.
> Tasks 1.3 and 1.4 both modify `routes.py`/`schemas.py` — run them sequentially.

---

### Task 1.1 [PARALLEL]: Test infrastructure + API key auth + CORS

**Files:**
- Create: `requirements.txt` (modify)
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `app/api/auth.py`
- Create: `tests/test_auth.py`
- Modify: `main.py`

- [ ] **Step 1: Add test dependencies to requirements.txt**

Append to `requirements.txt`:
```
pytest==8.2.0
pytest-asyncio==0.23.7
```

- [ ] **Step 2: Create tests package**

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:
```python
import pytest

pytest_plugins = ("anyio",)
```

- [ ] **Step 3: Write failing auth tests**

Create `tests/test_auth.py`:
```python
import os
import pytest
from fastapi import HTTPException
from unittest.mock import patch


@pytest.mark.asyncio
async def test_verify_api_key_valid():
    with patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"}):
        from app.api.auth import verify_api_key
        # Should not raise
        await verify_api_key(api_key="secret123")


@pytest.mark.asyncio
async def test_verify_api_key_invalid():
    with patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"}):
        from app.api.auth import verify_api_key
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="wrong")
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_missing():
    with patch.dict(os.environ, {"ADMIN_API_KEY": "secret123"}):
        from app.api.auth import verify_api_key
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key=None)
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_api_key_not_configured():
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ADMIN_API_KEY", None)
        from importlib import reload
        import app.api.auth
        reload(app.api.auth)
        from app.api.auth import verify_api_key
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="anything")
        assert exc_info.value.status_code == 500
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd /Users/liabenyehonatan/supermarket-prices
python -m pytest tests/test_auth.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'app.api.auth'`

- [ ] **Step 5: Create `app/api/auth.py`**

```python
import os
from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    expected = os.getenv("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=500, detail="ADMIN_API_KEY not configured on server")
    if api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
python -m pytest tests/test_auth.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Update `main.py` — CORS + apply auth to task routes**

Replace the existing CORS block and task endpoints in `main.py` with:

```python
import os
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.api.auth import verify_api_key

app = FastAPI(
    title="Israeli Supermarket Price Comparison API",
    description="Compare prices across Israeli supermarket chains",
    version="1.0.0",
)

_frontend_url = os.getenv("FRONTEND_URL")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_frontend_url] if _frontend_url else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root():
    return {"message": "Israeli Supermarket Price API", "docs": "/docs", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/v1/tasks/scrape", dependencies=[Depends(verify_api_key)])
async def trigger_scrape(chains: list[str] | None = None, skip_blocked: bool = True):
    from app.tasks import scrape_all
    task = scrape_all.delay(chains=chains, skip_blocked=skip_blocked)
    return {"task_id": task.id, "status": "queued"}


@app.post("/api/v1/tasks/parse", dependencies=[Depends(verify_api_key)])
async def trigger_parse(chains: list[str] | None = None):
    from app.tasks import parse_all
    task = parse_all.delay(chains=chains)
    return {"task_id": task.id, "status": "queued"}


@app.post("/api/v1/tasks/scrape-and-parse", dependencies=[Depends(verify_api_key)])
async def trigger_pipeline(chains: list[str] | None = None, skip_blocked: bool = True):
    from app.tasks import scrape_and_parse
    task = scrape_and_parse.delay(chains=chains, skip_blocked=skip_blocked)
    return {"task_id": task.id, "status": "queued"}


@app.post("/api/v1/tasks/geocode", dependencies=[Depends(verify_api_key)])
async def trigger_geocode():
    from app.tasks import geocode_new
    task = geocode_new.delay()
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
```

- [ ] **Step 8: Update `.env.example`**

Add to `.env.example` (create if it doesn't exist):
```
# Required for production
ADMIN_API_KEY=change-me-to-a-random-secret
FRONTEND_URL=https://your-domain.com

# Error monitoring (leave empty to disable)
SENTRY_DSN=

# Set to false on an Israeli VPS to enable FTP chains (Rami Levy, Osher Ad, etc.)
SKIP_BLOCKED_CHAINS=true

# Admin dashboard password (frontend)
ADMIN_PASSWORD=change-me
NEXT_PUBLIC_ADMIN_API_KEY=change-me-to-same-as-ADMIN_API_KEY
```

- [ ] **Step 9: Commit**

```bash
git add requirements.txt tests/ app/api/auth.py main.py .env.example
git commit -m "feat: API key auth on task endpoints, CORS from env, test infra"
```

---

### Task 1.2 [PARALLEL]: nginx.conf

**Files:**
- Create: `nginx/nginx.conf`

- [ ] **Step 1: Create `nginx/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;

    gzip on;
    gzip_vary on;
    gzip_types text/plain text/css application/json application/javascript text/javascript application/xml;

    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    # Next.js static assets — immutable, cache 1 year
    location /_next/static/ {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        add_header Cache-Control "public, max-age=31536000, immutable";
    }

    # FastAPI — all /api/* routes + docs
    location ~ ^/(api|docs|openapi\.json|redoc) {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }

    # Everything else → Next.js frontend
    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

- [ ] **Step 2: Verify docker-compose references match**

```bash
grep nginx docker-compose.yml
```

Expected output includes: `./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro`

- [ ] **Step 3: Commit**

```bash
git add nginx/nginx.conf
git commit -m "feat: add nginx reverse proxy config"
```

---

### Task 1.3: Basket ranking fix (backend + schema)

**Files:**
- Modify: `app/api/schemas.py`
- Modify: `app/api/routes.py`
- Create: `tests/test_basket_ranking.py`

- [ ] **Step 1: Write failing test for basket sort**

Create `tests/test_basket_ranking.py`:
```python
from decimal import Decimal


def _make_store_total(total_price, items_found, total_items):
    """Minimal dict mimicking BasketStoreTotal for sort testing."""
    return {
        "total_price": Decimal(str(total_price)),
        "items_found": items_found,
        "coverage_pct": items_found / total_items,
    }


def sort_stores(stores, total_items):
    for s in stores:
        s["coverage_pct"] = s["items_found"] / total_items
    return sorted(stores, key=lambda x: (-x["coverage_pct"], x["total_price"]))


def test_full_basket_beats_partial_cheaper_store():
    stores = [
        _make_store_total(30.0, 3, 5),   # partial, cheaper
        _make_store_total(45.0, 5, 5),   # full basket, more expensive
    ]
    sorted_stores = sort_stores(stores, 5)
    assert sorted_stores[0]["items_found"] == 5, "Full basket store must rank first"


def test_among_full_stores_cheapest_wins():
    stores = [
        _make_store_total(50.0, 5, 5),
        _make_store_total(42.0, 5, 5),
        _make_store_total(55.0, 5, 5),
    ]
    sorted_stores = sort_stores(stores, 5)
    assert sorted_stores[0]["total_price"] == Decimal("42.0")


def test_among_partial_stores_cheapest_wins():
    stores = [
        _make_store_total(20.0, 3, 5),
        _make_store_total(15.0, 3, 5),
    ]
    sorted_stores = sort_stores(stores, 5)
    assert sorted_stores[0]["total_price"] == Decimal("15.0")
```

- [ ] **Step 2: Run tests — verify they pass (pure logic, no imports)**

```bash
python -m pytest tests/test_basket_ranking.py -v
```

Expected: 3 passed.

- [ ] **Step 3: Update `app/api/schemas.py` — add `coverage_pct` and `transfer_url` to `BasketStoreTotal`**

Replace the `BasketStoreTotal` class:
```python
class BasketStoreTotal(BaseModel):
    store: StoreResponse
    total_price: Decimal
    items_found: int
    items_missing: int
    coverage_pct: float
    transfer_url: Optional[str]
    item_prices: List[dict]
```

- [ ] **Step 4: Update `compare_basket` in `app/api/routes.py`**

In the `# Step 5: Calculate total per store` block, replace the `store_totals.append(...)` call and the sort:

```python
        # coverage_pct: fraction of basket items this store carries
        items_found = len(barcode_prices)
        items_missing = len(barcodes) - items_found
        coverage_pct = items_found / len(barcodes)

        # transfer_url: link to this store's online shop
        from app.utils.transfer import get_transfer_url
        transfer_url = get_transfer_url(chain, store, barcodes)

        store_totals.append(BasketStoreTotal(
            store=StoreResponse(
                id=store.id,
                store_id=store.store_id,
                name=store.name,
                city=store.city,
                address=store.address,
                latitude=store.latitude,
                longitude=store.longitude,
                chain=ChainResponse(
                    id=chain.id,
                    name=chain.name,
                    chain_id=chain.chain_id,
                ),
            ),
            total_price=total,
            items_found=items_found,
            items_missing=items_missing,
            coverage_pct=coverage_pct,
            transfer_url=transfer_url,
            item_prices=list(barcode_prices.values()),
        ))

# Step 6: Sort — full-basket stores first, then cheapest within each tier
store_totals.sort(key=lambda x: (-x.coverage_pct, x.total_price))
```

Also remove the old `items_found = len(barcode_prices)` and `items_missing = ...` lines that were previously in the loop (they were above the append — now they're inside the new block above).

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas.py app/api/routes.py tests/test_basket_ranking.py
git commit -m "fix: basket stores ranked by coverage first, then price"
```

---

### Task 1.4: Transfer basket (utility + wire into routes)

**Files:**
- Create: `app/utils/__init__.py`
- Create: `app/utils/transfer.py`
- Create: `tests/test_transfer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_transfer.py`:
```python
from unittest.mock import MagicMock
from app.utils.transfer import get_transfer_url


def _chain(delivery_url=None, template=None, website=None):
    c = MagicMock()
    c.online_store_url_template = template
    c.website_url = website
    return c


def _store(delivery_url=None):
    s = MagicMock()
    s.delivery_url = delivery_url
    return s


def test_prefers_store_delivery_url():
    chain = _chain(template="https://chain.com/search?q={barcode}")
    store = _store(delivery_url="https://store.chain.com/branch42")
    result = get_transfer_url(chain, store, ["123456"])
    assert result == "https://store.chain.com/branch42"


def test_falls_back_to_chain_template():
    chain = _chain(template="https://chain.com/search?q={barcode}")
    store = _store(delivery_url=None)
    result = get_transfer_url(chain, store, ["7290000066885"])
    assert result == "https://chain.com/search?q=7290000066885"


def test_falls_back_to_website_url():
    chain = _chain(website="https://chain.com")
    store = _store(delivery_url=None)
    result = get_transfer_url(chain, store, ["123"])
    assert result == "https://chain.com"


def test_returns_none_when_no_urls():
    chain = _chain()
    store = _store()
    result = get_transfer_url(chain, store, ["123"])
    assert result is None
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
python -m pytest tests/test_transfer.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.utils'`

- [ ] **Step 3: Create `app/utils/__init__.py`** (empty)

- [ ] **Step 4: Create `app/utils/transfer.py`**

```python
from typing import Optional


def get_transfer_url(chain, store, barcodes: list[str]) -> Optional[str]:
    """
    Returns the best URL to send a user to complete their basket online.
    Priority: store delivery page > chain template > chain website > None.
    """
    if store.delivery_url:
        return store.delivery_url
    if chain.online_store_url_template and barcodes:
        return chain.online_store_url_template.replace("{barcode}", barcodes[0])
    if chain.website_url:
        return chain.website_url
    return None
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
python -m pytest tests/test_transfer.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app/utils/ tests/test_transfer.py
git commit -m "feat: transfer basket URL utility with store/chain fallback chain"
```

---

### Task 1.5 [PARALLEL]: Remove dead Vite code

**Files to delete** (all inside `frontend/src/`):
- `main.tsx`
- `App.tsx`
- `pages/` (directory)
- `styles/global.css`
- `vite-env.d.ts`
- `api/client.ts`

- [ ] **Step 1: Delete dead files**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend/src
rm -f main.tsx App.tsx vite-env.d.ts
rm -rf pages/ styles/ api/
```

- [ ] **Step 2: Verify Next.js still builds**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend
npx tsc --noEmit 2>&1 | head -30
```

Expected: no errors referencing the deleted files. If other TS errors appear, note them but don't fix them now.

- [ ] **Step 3: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add -A frontend/src/
git commit -m "chore: remove dead Vite/React files (main.tsx, App.tsx, pages/, styles/)"
```

---

## Phase 2 — Core Feature Gaps

> Tasks 2.1 and 2.4 are **[PARALLEL]** after 2.0 (schemas) is done.
> Tasks 2.2, 2.3, 2.5 are **[PARALLEL]** with each other.
> Frontend tasks 2.6–2.9 can start after their respective backend tasks complete.

---

### Task 2.0: New schemas (prerequisite for all Phase 2 backend tasks)

**Files:**
- Modify: `app/api/schemas.py`

- [ ] **Step 1: Add new schema classes to `app/api/schemas.py`**

Add after the existing classes (keep all existing classes intact):

```python
from datetime import timedelta


class PromotionResponse(BaseModel):
    promotion_id: str
    description: Optional[str]
    discounted_price: Optional[Decimal]
    min_qty: Optional[int]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    store_name: Optional[str]
    chain_name: str

    class Config:
        from_attributes = True


class PriceHistoryPoint(BaseModel):
    chain_name: str
    date: str        # "YYYY-MM-DD"
    price: float


class StatsResponse(BaseModel):
    products_count: int
    chains_count: int
    stores_count: int
    prices_count: int
    last_updated: Optional[datetime]


class CategoryCount(BaseModel):
    category: str
    count: int
```

Also update `PriceAtStore` to include an optional inline promotion:

```python
class PriceAtStore(BaseModel):
    store_id: int
    store_name: Optional[str]
    store_city: Optional[str]
    chain_name: str
    price: Decimal
    unit_price: Optional[Decimal]
    price_updated_at: datetime
    latitude: Optional[float]
    longitude: Optional[float]
    delivery_url: Optional[str]
    promotion: Optional["PromotionResponse"] = None   # inline best promotion

    class Config:
        from_attributes = True
```

- [ ] **Step 2: Commit**

```bash
git add app/api/schemas.py
git commit -m "feat: add PromotionResponse, PriceHistoryPoint, StatsResponse, CategoryCount schemas"
```

---

### Task 2.1 [PARALLEL]: Stats + categories + fuzzy search endpoints

**Files:**
- Modify: `app/api/routes.py`
- Create: `tests/test_search_logic.py`

- [ ] **Step 1: Write test for fuzzy search result ordering**

Create `tests/test_search_logic.py`:
```python
def test_exact_hits_before_fuzzy():
    """Exact substring matches should be ordered before fuzzy matches."""
    exact = ["טבסקו רוטב", "טבסקו ירוק"]
    fuzzy = ["טאבסקו"]  # simulated typo hit
    result = exact + fuzzy
    # Exact results come first (indices 0,1); fuzzy appended after
    assert result.index("טבסקו רוטב") < result.index("טאבסקו")
```

```bash
python -m pytest tests/test_search_logic.py -v
```

Expected: 1 passed (pure Python, no imports needed).

- [ ] **Step 2: Add stats endpoint to `app/api/routes.py`**

Add after the existing imports, add `or_` and `not_` to the sqlalchemy import:
```python
from sqlalchemy import select, func, and_, or_, not_
from datetime import timedelta
```

Add the new endpoint before the `compare_product_prices` route:

```python
@router.get("/stats", response_model=StatsResponse, summary="Live platform statistics")
async def get_stats(db: AsyncSession = Depends(get_db)):
    products_count = await db.scalar(select(func.count(Product.id))) or 0
    chains_count = await db.scalar(select(func.count(Chain.id))) or 0
    stores_count = await db.scalar(select(func.count(Store.id))) or 0
    prices_count = await db.scalar(
        select(func.count(Price.id)).where(Price.is_current == True)
    ) or 0
    last_updated = await db.scalar(
        select(func.max(Price.scraped_at)).where(Price.is_current == True)
    )
    return StatsResponse(
        products_count=products_count,
        chains_count=chains_count,
        stores_count=stores_count,
        prices_count=prices_count,
        last_updated=last_updated,
    )
```

- [ ] **Step 3: Add categories endpoint**

```python
@router.get("/categories", response_model=List[CategoryCount], summary="List product categories")
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product.category, func.count(Product.id).label("count"))
        .where(Product.category.isnot(None))
        .group_by(Product.category)
        .order_by(func.count(Product.id).desc())
        .limit(30)
    )
    return [CategoryCount(category=row.category, count=row.count) for row in result.all()]
```

- [ ] **Step 4: Update `search_products` to support fuzzy + category filter**

Replace the entire `search_products` function body:

```python
@router.get(
    "/products/search",
    response_model=List[ProductSearchResult],
    summary="Search products by name or barcode",
)
async def search_products(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    is_barcode = q.strip().isdigit()

    base_conditions = []
    if category:
        base_conditions.append(Product.category == category)

    if is_barcode:
        result = await db.execute(
            select(Product)
            .where(Product.barcode == q.strip(), *base_conditions)
            .limit(limit)
        )
        return result.scalars().all()

    # Stage 1: exact substring
    exact_result = await db.execute(
        select(Product)
        .where(Product.name.ilike(f"%{q}%"), *base_conditions)
        .limit(limit)
    )
    exact_products = exact_result.scalars().all()
    if len(exact_products) >= limit:
        return exact_products

    # Stage 2: trigram fuzzy hits for remaining slots
    exact_barcodes = [p.barcode for p in exact_products]
    remaining = limit - len(exact_products)

    fuzzy_conditions = [
        func.word_similarity(q, Product.name) > 0.25,
        *base_conditions,
    ]
    if exact_barcodes:
        fuzzy_conditions.append(not_(Product.barcode.in_(exact_barcodes)))

    fuzzy_result = await db.execute(
        select(Product)
        .where(*fuzzy_conditions)
        .order_by(func.word_similarity(q, Product.name).desc())
        .limit(remaining)
    )
    fuzzy_products = fuzzy_result.scalars().all()

    return exact_products + fuzzy_products
```

- [ ] **Step 5: Update schema imports in routes.py**

Add `StatsResponse`, `CategoryCount` to the import from `app.api.schemas`.

- [ ] **Step 6: Commit**

```bash
git add app/api/routes.py tests/test_search_logic.py
git commit -m "feat: stats endpoint, categories endpoint, fuzzy trigram search with category filter"
```

---

### Task 2.2 [PARALLEL]: Promotions endpoint + inline in compare

**Files:**
- Modify: `app/api/routes.py`

- [ ] **Step 1: Add promotions import to routes.py**

Add `Promotion` to the models import:
```python
from app.db.models import Product, Price, Store, Chain, Promotion
```

Add `PromotionResponse` to the schemas import.

- [ ] **Step 2: Add standalone promotions endpoint**

```python
@router.get(
    "/products/{barcode}/promotions",
    response_model=List[PromotionResponse],
    summary="Active promotions for a product",
)
async def get_promotions(barcode: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.barcode == barcode))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    from datetime import datetime as dt
    now = dt.utcnow()

    rows = (await db.execute(
        select(Promotion, Store, Chain)
        .join(Store, Promotion.store_id == Store.id)
        .join(Chain, Store.chain_id == Chain.id)
        .where(
            Promotion.product_id == product.id,
            Promotion.is_active == True,
            or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
        )
        .order_by(Promotion.discounted_price.asc())
    )).all()

    return [
        PromotionResponse(
            promotion_id=promo.promotion_id,
            description=promo.description,
            discounted_price=promo.discounted_price,
            min_qty=promo.min_qty,
            start_date=promo.start_date,
            end_date=promo.end_date,
            store_name=store.name,
            chain_name=chain.name,
        )
        for promo, store, chain in rows
    ]
```

- [ ] **Step 3: Attach best inline promotion to each `PriceAtStore` in `compare_product_prices`**

Inside `compare_product_prices`, after fetching `rows`, build a promotion lookup:

```python
    # Build promotion lookup: store_id → best active promotion
    from datetime import datetime as dt
    now = dt.utcnow()
    promo_rows = (await db.execute(
        select(Promotion, Store)
        .join(Store, Promotion.store_id == Store.id)
        .where(
            Promotion.product_id == product.id,
            Promotion.is_active == True,
            or_(Promotion.end_date.is_(None), Promotion.end_date >= now),
        )
        .order_by(Promotion.discounted_price.asc())
    )).all()

    best_promo: dict[int, Promotion] = {}
    promo_chain_map: dict[int, Chain] = {}
    for promo, store in promo_rows:
        if store.id not in best_promo:
            best_promo[store.id] = promo
```

Then when building `price_list`, pass the promotion:

```python
    for price, store, chain in rows:
        promo = best_promo.get(store.id)
        price_list.append(PriceAtStore(
            store_id=store.id,
            store_name=store.name,
            store_city=store.city,
            chain_name=chain.name,
            price=price.price,
            unit_price=price.unit_price,
            price_updated_at=price.price_updated_at,
            latitude=store.latitude,
            longitude=store.longitude,
            delivery_url=store.delivery_url,
            promotion=PromotionResponse(
                promotion_id=promo.promotion_id,
                description=promo.description,
                discounted_price=promo.discounted_price,
                min_qty=promo.min_qty,
                start_date=promo.start_date,
                end_date=promo.end_date,
                store_name=store.name,
                chain_name=chain.name,
            ) if promo else None,
        ))
```

- [ ] **Step 4: Commit**

```bash
git add app/api/routes.py
git commit -m "feat: promotions endpoint + inline best promotion on product compare"
```

---

### Task 2.3 [PARALLEL]: Price history endpoint

**Files:**
- Modify: `app/api/routes.py`

- [ ] **Step 1: Add history endpoint**

```python
@router.get(
    "/products/{barcode}/history",
    response_model=List[PriceHistoryPoint],
    summary="Price history for a product (last N days)",
)
async def get_price_history(
    barcode: str,
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.barcode == barcode))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    from datetime import datetime as dt, timedelta
    cutoff = dt.utcnow() - timedelta(days=days)

    # Top 5 chains by historical data volume for this product
    chain_count_q = (
        select(Chain.name, func.count(Price.id).label("cnt"))
        .join(Store, Price.store_id == Store.id)
        .join(Chain, Store.chain_id == Chain.id)
        .where(Price.product_id == product.id, Price.price_updated_at >= cutoff)
        .group_by(Chain.name)
        .order_by(func.count(Price.id).desc())
        .limit(5)
    )
    chain_rows = (await db.execute(chain_count_q)).all()
    top_chains = [r.name for r in chain_rows]

    if not top_chains:
        return []

    # Daily min price per chain
    history_q = (
        select(
            Chain.name.label("chain_name"),
            func.date(Price.price_updated_at).label("date"),
            func.min(Price.price).label("price"),
        )
        .join(Store, Price.store_id == Store.id)
        .join(Chain, Store.chain_id == Chain.id)
        .where(
            Price.product_id == product.id,
            Price.price_updated_at >= cutoff,
            Chain.name.in_(top_chains),
        )
        .group_by(Chain.name, func.date(Price.price_updated_at))
        .order_by(Chain.name, func.date(Price.price_updated_at))
    )
    rows = (await db.execute(history_q)).all()

    return [
        PriceHistoryPoint(chain_name=r.chain_name, date=str(r.date), price=float(r.price))
        for r in rows
    ]
```

Add `PriceHistoryPoint` to the schemas import line.

- [ ] **Step 2: Commit**

```bash
git add app/api/routes.py
git commit -m "feat: price history endpoint with daily min per chain"
```

---

### Task 2.4 [PARALLEL]: Near-me location filter (backend)

**Files:**
- Create: `app/utils/haversine.py`
- Create: `tests/test_haversine.py`
- Modify: `app/api/routes.py`

- [ ] **Step 1: Write failing haversine tests**

Create `tests/test_haversine.py`:
```python
from app.utils.haversine import haversine_km


def test_same_point_is_zero():
    assert haversine_km(32.07, 34.78, 32.07, 34.78) == 0.0


def test_tel_aviv_to_jerusalem_approx_60km():
    # Tel Aviv (32.07, 34.78) to Jerusalem (31.77, 35.21)
    dist = haversine_km(32.07, 34.78, 31.77, 35.21)
    assert 55 < dist < 70, f"Expected ~60km, got {dist:.1f}km"


def test_tel_aviv_to_haifa_approx_90km():
    dist = haversine_km(32.07, 34.78, 32.81, 34.99)
    assert 80 < dist < 100, f"Expected ~90km, got {dist:.1f}km"
```

```bash
python -m pytest tests/test_haversine.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'app.utils.haversine'`

- [ ] **Step 2: Create `app/utils/haversine.py`**

```python
import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two GPS coordinates."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
```

- [ ] **Step 3: Run tests — verify they pass**

```bash
python -m pytest tests/test_haversine.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Add location params to `compare_basket` in routes.py**

Change the function signature:
```python
async def compare_basket(
    items: List[BasketItem],
    lat: Optional[float] = Query(None, description="User latitude for near-me filter"),
    lng: Optional[float] = Query(None, description="User longitude for near-me filter"),
    radius_km: float = Query(20.0, gt=0, le=200, description="Filter radius in km"),
    db: AsyncSession = Depends(get_db),
):
```

Add location filtering after `# Step 4: Group prices by store` (after building `store_prices`, `store_objects`, `chain_objects`):

```python
    # Location filter — keep only stores within radius if lat/lng provided
    if lat is not None and lng is not None:
        from app.utils.haversine import haversine_km
        store_prices = {
            sid: prices
            for sid, prices in store_prices.items()
            if store_objects[sid].latitude is not None
            and haversine_km(lat, lng, store_objects[sid].latitude, store_objects[sid].longitude) <= radius_km
        }
        store_objects = {sid: s for sid, s in store_objects.items() if sid in store_prices}
        chain_objects = {sid: c for sid, c in chain_objects.items() if sid in store_prices}

        if not store_prices:
            return BasketCompareResponse(
                stores=[],
                total_items_requested=len(barcodes),
                cheapest_store=None,
                max_savings=Decimal("0"),
            )
```

Also add the same params + filter to `compare_product_prices`:
```python
async def compare_product_prices(
    barcode: str,
    lat: Optional[float] = Query(None),
    lng: Optional[float] = Query(None),
    radius_km: float = Query(20.0, gt=0, le=200),
    db: AsyncSession = Depends(get_db),
):
```

After building `rows` in `compare_product_prices`, filter:
```python
    if lat is not None and lng is not None:
        from app.utils.haversine import haversine_km
        rows = [
            (price, store, chain) for price, store, chain in rows
            if store.latitude is not None
            and haversine_km(lat, lng, store.latitude, store.longitude) <= radius_km
        ]
        if not rows:
            raise HTTPException(status_code=404, detail="No stores within radius have this product")
```

- [ ] **Step 5: Commit**

```bash
git add app/utils/haversine.py tests/test_haversine.py app/api/routes.py
git commit -m "feat: near-me location filter on basket and product compare endpoints"
```

---

### Task 2.5 [PARALLEL]: Geocoder pipeline integration

**Files:**
- Modify: `app/geocoder.py`
- Modify: `app/tasks.py`
- Modify: `app/celery_app.py`
- Modify: `app/parser/mass_parser.py`

- [ ] **Step 1: Add `only_missing` param to `geocode_all_stores` in `app/geocoder.py`**

Change the function signature and WHERE clause:
```python
async def geocode_all_stores(dry_run: bool = False, only_missing: bool = True):
    """Geocode stores. When only_missing=True, skips stores that already have coordinates."""
    async with AsyncSessionLocal() as session:
        q = (
            select(Store, Chain.name)
            .join(Chain, Store.chain_id == Chain.id)
            .order_by(Store.id)
        )
        if only_missing:
            q = q.where(Store.latitude.is_(None))
        result = await session.execute(q)
        rows = result.all()
    # rest of function unchanged
```

- [ ] **Step 2: Add `geocode_new` task to `app/tasks.py`**

Remove the entire `_run_async` helper. Then replace the two `_run_async(...)` calls with `asyncio.run(...)`:

In `parse_all`:
```python
    asyncio.run(run_mass_parser(chains=chains))
```

In `scrape_and_parse`:
```python
    asyncio.run(run_mass_parser(chains=chains))
```

Add the new task at the end of the file:
```python
@app.task(bind=True, name="app.tasks.geocode_new")
def geocode_new(self):
    """Geocode any stores that are missing latitude/longitude."""
    from app.geocoder import geocode_all_stores
    logger.info(f"[Task {self.request.id}] Geocoding new stores")
    self.update_state(state="GEOCODING")
    asyncio.run(geocode_all_stores(only_missing=True))
    logger.info(f"[Task {self.request.id}] Geocoding finished")
    return {"status": "done", "task": "geocode_new"}
```

- [ ] **Step 3: Add geocode to celery beat schedule in `app/celery_app.py`**

```python
SKIP_BLOCKED = os.getenv("SKIP_BLOCKED_CHAINS", "true").lower() == "true"

app.conf.beat_schedule = {
    "scrape-and-parse-every-3h": {
        "task": "app.tasks.scrape_and_parse",
        "schedule": crontab(minute=0, hour="*/3"),
        "kwargs": {"skip_blocked": SKIP_BLOCKED},
    },
    "full-scrape-nightly": {
        "task": "app.tasks.scrape_and_parse",
        "schedule": crontab(minute=0, hour=2),
        "kwargs": {"skip_blocked": SKIP_BLOCKED},
    },
    "geocode-new-stores-nightly": {
        "task": "app.tasks.geocode_new",
        "schedule": crontab(minute=30, hour=2),   # 30 min after nightly scrape
    },
}
```

- [ ] **Step 4: Commit**

```bash
git add app/geocoder.py app/tasks.py app/celery_app.py
git commit -m "feat: geocode_new Celery task, remove _run_async, SKIP_BLOCKED_CHAINS env var"
```

---

### Task 2.6: Admin chain-stats endpoint

**Files:**
- Modify: `app/api/routes.py`

- [ ] **Step 1: Add the chain-stats endpoint**

Add to `app/api/routes.py` (import `verify_api_key` at top):
```python
from app.api.auth import verify_api_key
```

Then add the endpoint:
```python
@router.get("/admin/chain-stats", summary="Per-chain operational stats (admin)")
async def get_chain_stats(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    rows = (await db.execute(
        select(
            Chain.name,
            func.count(func.distinct(Store.id)).label("stores_total"),
            func.count(func.distinct(Store.id)).filter(Store.latitude.isnot(None)).label("stores_geocoded"),
            func.max(Price.scraped_at).label("last_scraped"),
            func.count(func.distinct(Price.product_id)).filter(Price.is_current == True).label("products_parsed"),
        )
        .outerjoin(Store, Store.chain_id == Chain.id)
        .outerjoin(Price, and_(Price.store_id == Store.id))
        .where(Chain.is_active == True)
        .group_by(Chain.id, Chain.name)
        .order_by(Chain.name)
    )).all()

    return [
        {
            "chain_name": row.name,
            "last_scraped": row.last_scraped,
            "products_parsed": row.products_parsed or 0,
            "stores_total": row.stores_total or 0,
            "stores_geocoded": row.stores_geocoded or 0,
            "geocoding_pct": round(
                (row.stores_geocoded or 0) / max(row.stores_total or 1, 1) * 100, 1
            ),
        }
        for row in rows
    ]
```

- [ ] **Step 2: Commit**

```bash
git add app/api/routes.py
git commit -m "feat: admin chain-stats endpoint (API-key protected)"
```

---

### Task 2.7: Frontend — `api.ts` updates + StatsBar live data

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/layout/StatsBar.tsx`

- [ ] **Step 1: Update `frontend/src/lib/api.ts`**

Replace the entire file:
```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface Product {
  id: number;
  barcode: string;
  name: string;
  brand?: string;
  image_url?: string;
  unit_of_measure?: string;
  is_weighted: boolean;
}

export interface PromotionInfo {
  promotion_id: string;
  description?: string;
  discounted_price?: number;
  min_qty?: number;
  end_date?: string;
  store_name?: string;
  chain_name: string;
}

export interface PriceAtStore {
  store_id: number;
  store_name?: string;
  store_city?: string;
  chain_name: string;
  price: number;
  unit_price?: number;
  price_updated_at: string;
  latitude?: number;
  longitude?: number;
  delivery_url?: string;
  promotion?: PromotionInfo;
}

export interface ProductCompareResponse {
  product: Product;
  prices: PriceAtStore[];
  cheapest_price: number;
  most_expensive_price: number;
  price_difference: number;
}

export interface BasketStoreTotal {
  store: {
    id: number;
    store_id: string;
    name?: string;
    city?: string;
    address?: string;
    latitude?: number;
    longitude?: number;
    chain: { id: number; name: string; chain_id: string };
  };
  total_price: number;
  items_found: number;
  items_missing: number;
  coverage_pct: number;
  transfer_url?: string;
  item_prices: Array<{
    barcode: string;
    product_name: string;
    unit_price: number;
    quantity: number;
    line_total: number;
  }>;
}

export interface BasketCompareResponse {
  stores: BasketStoreTotal[];
  total_items_requested: number;
  cheapest_store?: string;
  max_savings: number;
}

export interface PriceHistoryPoint {
  chain_name: string;
  date: string;
  price: number;
}

export interface StatsData {
  products_count: number;
  chains_count: number;
  stores_count: number;
  prices_count: number;
  last_updated?: string;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export async function searchProducts(q: string, limit = 20, category?: string): Promise<Product[]> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  if (category) params.set("category", category);
  const res = await fetch(`${API_BASE}/api/v1/products/search?${params}`);
  if (!res.ok) return [];
  return res.json();
}

export async function compareProduct(
  barcode: string,
  location?: { lat: number; lng: number; radius_km?: number }
): Promise<ProductCompareResponse | null> {
  const params = new URLSearchParams();
  if (location) {
    params.set("lat", String(location.lat));
    params.set("lng", String(location.lng));
    if (location.radius_km) params.set("radius_km", String(location.radius_km));
  }
  const qs = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API_BASE}/api/v1/products/${barcode}/compare${qs}`);
  if (!res.ok) return null;
  return res.json();
}

export async function compareBasket(
  items: Array<{ barcode: string; quantity: number }>,
  location?: { lat: number; lng: number; radius_km?: number }
): Promise<BasketCompareResponse | null> {
  const params = new URLSearchParams();
  if (location) {
    params.set("lat", String(location.lat));
    params.set("lng", String(location.lng));
    if (location.radius_km) params.set("radius_km", String(location.radius_km));
  }
  const qs = params.toString() ? `?${params}` : "";
  const res = await fetch(`${API_BASE}/api/v1/basket/compare${qs}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });
  if (!res.ok) return null;
  return res.json();
}

export async function getProductHistory(barcode: string, days = 30): Promise<PriceHistoryPoint[]> {
  const res = await fetch(`${API_BASE}/api/v1/products/${barcode}/history?days=${days}`);
  if (!res.ok) return [];
  return res.json();
}

export async function getStats(): Promise<StatsData | null> {
  const res = await fetch(`${API_BASE}/api/v1/stats`);
  if (!res.ok) return null;
  return res.json();
}

export async function getCategories(): Promise<CategoryCount[]> {
  const res = await fetch(`${API_BASE}/api/v1/categories`);
  if (!res.ok) return [];
  return res.json();
}

export async function getChainStats(apiKey: string): Promise<unknown[]> {
  const res = await fetch(`${API_BASE}/api/v1/admin/chain-stats`, {
    headers: { "X-Api-Key": apiKey },
  });
  if (!res.ok) return [];
  return res.json();
}
```

- [ ] **Step 2: Rewrite `frontend/src/components/layout/StatsBar.tsx`**

```tsx
"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { getStats, StatsData } from "@/lib/api";

export default function StatsBar() {
  const t = useTranslations("stats");
  const [stats, setStats] = useState<StatsData | null>(null);

  useEffect(() => {
    getStats().then(setStats).catch(() => {});
  }, []);

  const fmt = (n: number) => n.toLocaleString("he-IL");

  return (
    <div className="border-b border-gray-200">
      <div className="max-w-6xl mx-auto px-5 py-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <span className="font-mono text-xl text-gray-900 tracking-tight">
              {stats ? `${fmt(stats.products_count)}+` : <span className="text-gray-300">—</span>}
            </span>
            <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mt-0.5">
              {t("products")}
            </p>
          </div>
          <div>
            <span className="font-mono text-xl text-gray-900 tracking-tight">
              {stats ? String(stats.chains_count) : <span className="text-gray-300">—</span>}
            </span>
            <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mt-0.5">
              {t("chains")}
            </p>
          </div>
          <div>
            <span className="font-mono text-xl text-gray-900 tracking-tight">
              {stats ? `${fmt(stats.stores_count)}+` : <span className="text-gray-300">—</span>}
            </span>
            <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mt-0.5">
              {t("stores")}
            </p>
          </div>
          <div>
            {stats?.last_updated && (
              <span className="font-mono text-sm text-gray-600 tracking-tight">
                {new Date(stats.last_updated).toLocaleTimeString("he-IL", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
            <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mt-0.5">
              {t("updatedEvery")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add frontend/src/lib/api.ts frontend/src/components/layout/StatsBar.tsx
git commit -m "feat: StatsBar fetches live data, api.ts updated with all new endpoints"
```

---

### Task 2.8: Frontend — basket results (coverage divider + transfer CTA + freshness)

**Files:**
- Modify: `frontend/src/components/basket/BasketResults.tsx`

- [ ] **Step 1: Replace `BasketResults.tsx`**

```tsx
"use client";

import { useTranslations, useLocale } from "next-intl";
import { useEffect, useState } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { BasketCompareResponse } from "@/lib/api";

function CountUp({ to, prefix = "" }: { to: number; prefix?: string }) {
  const raw = useMotionValue(0);
  const spring = useSpring(raw, { stiffness: 45, damping: 12 });
  const [display, setDisplay] = useState("0.00");
  useEffect(() => { raw.set(to); }, [to, raw]);
  useEffect(() => spring.on("change", (v) => setDisplay(v.toFixed(2))), [spring]);
  return <>{prefix}{display}</>;
}

function relativeTime(isoString: string, locale: string): string {
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffH = Math.floor(diffMs / 3600000);
  const diffD = Math.floor(diffMs / 86400000);
  if (locale === "he") {
    if (diffH < 1) return "עודכן לאחרונה";
    if (diffH < 24) return `עודכן לפני ${diffH}ש׳`;
    return `עודכן לפני ${diffD}י׳`;
  }
  if (diffH < 1) return "just updated";
  if (diffH < 24) return `updated ${diffH}h ago`;
  return `updated ${diffD}d ago`;
}

export default function BasketResults({ results }: { results: BasketCompareResponse }) {
  const t = useTranslations("basket");
  const tC = useTranslations("common");
  const locale = useLocale();
  const isRtl = locale === "he";

  const fullStores = results.stores.filter((s) => s.coverage_pct === 1);
  const partialStores = results.stores.filter((s) => s.coverage_pct < 1);
  const best = results.stores[0];
  const savings = Number(results.max_savings);

  return (
    <div className="space-y-3 mt-3">
      {savings > 0.01 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
          className="border border-brand-200 bg-brand-50 rounded-xl px-4 py-2.5 flex items-center gap-3">
          <div className="w-5 h-5 rounded-full border border-brand-200 bg-brand-100 flex items-center justify-center flex-shrink-0">
            <svg className="w-3 h-3 text-brand-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <span className="text-sm text-brand-700">
            {isRtl ? `חיסכון אפשרי של ${tC("nis")}${savings.toFixed(2)}` : `Save up to ${tC("nis")}${savings.toFixed(2)}`}
          </span>
        </motion.div>
      )}

      {best && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
          className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-2 mb-0.5">
                  <span className="text-[10px] font-semibold tracking-widest uppercase text-gray-300">01</span>
                  <span className="text-[10px] font-semibold tracking-wide uppercase text-brand-600 bg-brand-50 border border-brand-100 px-2 py-0.5 rounded">
                    {t("cheapestStore")}
                  </span>
                </div>
                <p className={`text-xl text-gray-900 leading-tight truncate ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
                  {best.store.chain.name}
                </p>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  {[best.store.name, best.store.city].filter(Boolean).join(" · ")}
                  {best.items_missing > 0 && (
                    <span className="text-amber-500"> · {best.items_missing} {t("missing")}</span>
                  )}
                </p>
              </div>
              <div className="text-end flex-shrink-0">
                <p className="font-mono text-3xl text-gray-900 tabular-nums leading-none">
                  <CountUp to={Number(best.total_price)} prefix={tC("nis")} />
                </p>
              </div>
            </div>
          </div>
          <div className="px-4 pb-4">
            {best.transfer_url ? (
              <a
                href={best.transfer_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-sm font-semibold transition-colors text-center"
              >
                {t("transferBasket")} — {best.store.chain.name}
              </a>
            ) : (
              <button
                disabled
                className="w-full py-2.5 rounded-lg bg-gray-100 text-gray-400 text-sm font-semibold cursor-not-allowed"
                title={isRtl ? "אין חנות מקוונת" : "No online store"}
              >
                {t("transferBasket")} — {best.store.chain.name}
              </button>
            )}
          </div>
        </motion.div>
      )}

      {/* Ranks 2-3 */}
      {results.stores.slice(1, 3).length > 0 && (
        <div className={`grid gap-2 ${results.stores[2] ? "grid-cols-2" : "grid-cols-1"}`}>
          {results.stores.slice(1, 3).map((s, i) => {
            const d = Number(s.total_price) - Number(best.total_price);
            return (
              <motion.div key={s.store.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.08 + i * 0.06 }}
                className="border border-gray-200 rounded-xl p-3 hover:border-gray-300 transition-colors">
                <span className="text-[10px] font-semibold tracking-widest text-gray-300 uppercase block mb-0.5">
                  {String(i + 2).padStart(2, "0")}
                </span>
                <p className={`text-base text-gray-900 leading-tight truncate ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
                  {s.store.chain.name}
                </p>
                {s.store.city && <p className="text-[10px] text-gray-400 mt-0.5 truncate">{s.store.city}</p>}
                <p className="font-mono text-lg text-gray-700 mt-1.5 tabular-nums">
                  {tC("nis")}{Number(s.total_price).toFixed(2)}
                </p>
                {d > 0.01 && <p className="text-[10px] text-amber-500">+{tC("nis")}{d.toFixed(2)}</p>}
                {s.items_missing > 0 && (
                  <p className="text-[10px] text-amber-500 mt-0.5">{s.items_missing} {t("missing")}</p>
                )}
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Remaining stores */}
      {results.stores.slice(3).length > 0 && (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="divide-y divide-gray-100">
            {results.stores.slice(3).map((s, i) => {
              const d = Number(s.total_price) - Number(best.total_price);
              return (
                <div key={s.store.id} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="text-[10px] font-semibold text-gray-300 w-6 flex-shrink-0">
                    {String(i + 4).padStart(2, "0")}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-900 truncate">{s.store.chain.name}</p>
                    {s.store.city && <p className="text-[10px] text-gray-400">{s.store.city}</p>}
                    {s.items_missing > 0 && (
                      <p className="text-[10px] text-amber-500">{s.items_missing} {t("missing")}</p>
                    )}
                  </div>
                  <div className="text-end flex-shrink-0">
                    <p className="font-mono text-sm text-gray-700 tabular-nums">
                      {tC("nis")}{Number(s.total_price).toFixed(2)}
                    </p>
                    {d > 0.01 && <p className="text-[10px] text-amber-500">+{tC("nis")}{d.toFixed(2)}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Partial stores separator */}
      {fullStores.length > 0 && partialStores.length > 0 && (
        <p className="text-[10px] text-gray-400 text-center pt-1">
          {isRtl ? "↓ סניפים עם חלק מהפריטים בלבד" : "↓ Stores with partial basket only"}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend && npx tsc --noEmit 2>&1 | grep "BasketResults" | head -10
```

Expected: no errors on BasketResults.tsx.

- [ ] **Step 3: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add frontend/src/components/basket/BasketResults.tsx
git commit -m "feat: basket results — real transfer URL, coverage divider, partial store badges"
```

---

### Task 2.9: Frontend — product page (sparkline + promotions + freshness)

**Files:**
- Modify: `frontend/src/app/[locale]/product/[barcode]/page.tsx`

- [ ] **Step 1: Update the product page**

Replace the entire file:
```tsx
"use client";

import { useTranslations, useLocale } from "next-intl";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { compareProduct, getProductHistory, ProductCompareResponse, PriceHistoryPoint } from "@/lib/api";
import { useBasket } from "@/lib/basket-store";
import { Button } from "@/components/ui/button";
import { SparklineSection } from "@/components/PriceSparkline";
import Image from "next/image";

function relativeTime(iso: string, locale: string): string {
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000);
  const d = Math.floor(h / 24);
  if (locale === "he") {
    if (h < 1) return "עודכן זה עתה";
    if (h < 24) return `עודכן לפני ${h}ש׳`;
    return `עודכן לפני ${d}י׳`;
  }
  if (h < 1) return "just updated";
  if (h < 24) return `updated ${h}h ago`;
  return `updated ${d}d ago`;
}

export default function ProductPage() {
  const t = useTranslations("product");
  const tC = useTranslations("common");
  const locale = useLocale();
  const isRtl = locale === "he";
  const params = useParams();
  const barcode = params.barcode as string;
  const { addItem } = useBasket();

  const [data, setData] = useState<ProductCompareResponse | null>(null);
  const [history, setHistory] = useState<PriceHistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    Promise.all([
      compareProduct(barcode),
      getProductHistory(barcode, 30),
    ])
      .then(([compareRes, histRes]) => {
        setData(compareRes);
        setHistory(histRes);
        setLoading(false);
      })
      .catch(() => { setError(true); setLoading(false); });
  }, [barcode]);

  if (loading) return (
    <div className="max-w-3xl mx-auto px-5 py-20 text-center text-gray-400 text-sm">{tC("loading")}</div>
  );
  if (error || !data) return (
    <div className="max-w-3xl mx-auto px-5 py-20 text-center">
      <p className="text-gray-400 text-sm mb-4">{tC("error")}</p>
      <Button variant="secondary" onClick={() => window.location.reload()}>{tC("retry")}</Button>
    </div>
  );

  const { product, prices } = data;
  const cheapest_price = Number(data.cheapest_price);
  const most_expensive_price = Number(data.most_expensive_price);
  const price_difference = Number(data.price_difference);

  // For sparkline: group history by chain, pick cheapest store per day
  const chainPriceMap: Record<string, number[]> = {};
  history.forEach((h) => {
    if (!chainPriceMap[h.chain_name]) chainPriceMap[h.chain_name] = [];
    chainPriceMap[h.chain_name].push(h.price);
  });
  const sparkPrices = Object.values(chainPriceMap)[0] ?? [];

  return (
    <div className="max-w-3xl mx-auto px-5 py-10">
      {/* Product header */}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
        className="flex items-start gap-5 mb-8 pb-8 border-b border-gray-200">
        <div className="w-20 h-20 rounded-xl bg-gray-100 flex-shrink-0 overflow-hidden flex items-center justify-center">
          {product.image_url ? (
            <Image src={product.image_url} alt={product.name} width={80} height={80}
              className="object-contain w-full h-full"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
          ) : (
            <span className="text-xs text-gray-300">{t("noImage")}</span>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h1 className={`text-xl text-gray-900 leading-tight mb-1 ${isRtl ? "font-hebrew font-black" : "font-bold"}`}>
            {product.name}
          </h1>
          {product.brand && <p className="text-sm text-gray-400 mb-2">{product.brand}</p>}
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-400">
            <span>{t("barcode")}: {product.barcode}</span>
            {product.unit_of_measure && <span>{product.unit_of_measure}</span>}
          </div>
          <div className="mt-3">
            <Button size="sm" onClick={() => addItem({ barcode: product.barcode, name: product.name, brand: product.brand, imageUrl: product.image_url })}>
              {t("addToBasket")}
            </Button>
          </div>
        </div>
      </motion.div>

      {/* Price summary */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.1 }}
        className="grid grid-cols-3 gap-3 mb-6">
        <div className="bg-brand-50 border border-brand-100 rounded-xl p-4 text-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-brand-600 mb-1">{isRtl ? "הזול" : "Cheapest"}</p>
          <p className="font-mono text-2xl text-gray-900 tabular-nums">{tC("nis")}{cheapest_price.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mb-1">{isRtl ? "היקר" : "Most expensive"}</p>
          <p className="font-mono text-2xl text-gray-900 tabular-nums">{tC("nis")}{most_expensive_price.toFixed(2)}</p>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-gray-400 mb-1">{isRtl ? "הפרש" : "Difference"}</p>
          <p className="font-mono text-2xl text-gray-900 tabular-nums">{tC("nis")}{price_difference.toFixed(2)}</p>
        </div>
      </motion.div>

      {/* Sparkline */}
      {sparkPrices.length >= 2 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}
          className="mb-8 border border-gray-200 rounded-xl p-4">
          <SparklineSection prices={sparkPrices} />
        </motion.div>
      )}

      {/* Price list */}
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.2 }}>
        <h2 className={`text-lg text-gray-900 mb-4 ${isRtl ? "font-hebrew font-bold" : "font-bold"}`}>
          {t("price")} {isRtl ? "בסניפים" : "by store"} ({prices.length})
        </h2>
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="divide-y divide-gray-100">
            {prices.map((p, i) => {
              const isCheapest = Number(p.price) === cheapest_price;
              return (
                <div key={`${p.store_id}-${i}`}
                  className={`px-4 py-3 ${isCheapest ? "bg-brand-50/50" : ""}`}>
                  <div className="flex items-center gap-3">
                    <span className="text-[10px] font-semibold tracking-widest text-gray-300 w-7 flex-shrink-0">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm text-gray-900 truncate ${isCheapest ? "font-semibold" : ""}`}>
                        {p.chain_name}
                      </p>
                      <p className="text-[10px] text-gray-400 truncate">
                        {[p.store_name, p.store_city].filter(Boolean).join(" · ")}
                        {" · "}
                        <span className="text-gray-300">{relativeTime(p.price_updated_at, locale)}</span>
                      </p>
                    </div>
                    <div className="text-end flex-shrink-0">
                      <p className={`font-mono text-sm tabular-nums ${isCheapest ? "text-brand-700 font-semibold" : "text-gray-700"}`}>
                        {tC("nis")}{Number(p.price).toFixed(2)}
                      </p>
                      {p.unit_price && (
                        <p className="text-[10px] text-gray-400">
                          {tC("nis")}{Number(p.unit_price).toFixed(2)}/{product.unit_of_measure || (isRtl ? "יח׳" : "unit")}
                        </p>
                      )}
                    </div>
                  </div>
                  {p.promotion && (
                    <div className="mt-1.5 ms-10 flex items-center gap-1.5">
                      <span className="text-[10px] font-semibold bg-green-50 text-green-700 border border-green-200 rounded px-2 py-0.5">
                        {p.promotion.description || (isRtl ? "מבצע" : "Promotion")}
                        {p.promotion.discounted_price && ` · ${tC("nis")}${Number(p.promotion.discounted_price).toFixed(2)}`}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend && npx tsc --noEmit 2>&1 | grep "product\[barcode\]" | head -10
```

- [ ] **Step 3: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add "frontend/src/app/[locale]/product/[barcode]/page.tsx"
git commit -m "feat: product page — price sparkline, inline promotions, freshness timestamps"
```

---

### Task 2.10: Frontend — BasketBuilder near-me toggle + search category chips

**Files:**
- Modify: `frontend/src/components/basket/BasketBuilder.tsx`
- Modify: `frontend/src/app/[locale]/search/page.tsx`

- [ ] **Step 1: Add near-me toggle to `BasketBuilder.tsx`**

Add location state and update `handleCompare`:
```tsx
  const [location, setLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [locationError, setLocationError] = useState(false);

  const handleNearMe = () => {
    if (!navigator.geolocation) { setLocationError(true); return; }
    navigator.geolocation.getCurrentPosition(
      (pos) => { setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }); setLocationError(false); },
      () => { setLocationError(true); }
    );
  };

  const handleCompare = async () => {
    if (!items.length) return;
    setComparing(true); setResults(null);
    const res = await compareBasket(
      items.map((i) => ({ barcode: i.barcode, quantity: i.quantity })),
      location ?? undefined
    );
    setResults(res); setComparing(false);
  };
```

Add the near-me button above the compare button (inside the basket items block, before the `<Button onClick={handleCompare}>`):
```tsx
              <div className="flex items-center justify-between px-4 pb-2">
                <button
                  onClick={handleNearMe}
                  className={`text-[11px] font-semibold flex items-center gap-1 transition-colors ${
                    location ? "text-brand-600" : "text-gray-400 hover:text-gray-600"
                  }`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {location ? (isRtl ? "מיקום פעיל" : "Near me ON") : (isRtl ? "סנן לפי מיקום" : "Near me")}
                </button>
                {locationError && (
                  <span className="text-[10px] text-red-400">{isRtl ? "לא ניתן לגשת למיקום" : "Location denied"}</span>
                )}
              </div>
```

Also update the `compareBasket` import to match the new signature with location param.

- [ ] **Step 2: Add category chips to `SearchPage`**

At the top of the `SearchPage` component, fetch categories:
```tsx
  const [categories, setCategories] = useState<Array<{ category: string; count: number }>>([]);
  const [activeCategory, setActiveCategory] = useState<string | undefined>();

  useEffect(() => {
    getCategories().then(setCategories).catch(() => {});
  }, []);
```

Update `handleSearch` to pass category:
```tsx
  const handleSearch = (q: string, cat?: string) => {
    setQuery(q);
    const category = cat ?? activeCategory;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim() && !category) { setResults([]); setSearched(false); return; }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      const res = await searchProducts(q || " ", 50, category);
      setResults(res);
      setSearched(true);
      setLoading(false);
    }, 300);
  };
```

Add chip row above the search input:
```tsx
      {categories.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1 mb-4 no-scrollbar">
          <button
            onClick={() => { setActiveCategory(undefined); handleSearch(query, undefined); }}
            className={`flex-shrink-0 px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors ${
              !activeCategory ? "bg-brand-600 text-white border-brand-600" : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
            }`}
          >
            {isRtl ? "הכל" : "All"}
          </button>
          {categories.slice(0, 12).map((c) => (
            <button
              key={c.category}
              onClick={() => { setActiveCategory(c.category); handleSearch(query, c.category); }}
              className={`flex-shrink-0 px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors ${
                activeCategory === c.category ? "bg-brand-600 text-white border-brand-600" : "bg-white text-gray-600 border-gray-200 hover:border-gray-300"
              }`}
            >
              {c.category}
            </button>
          ))}
        </div>
      )}
```

Add `getCategories` to the import from `@/lib/api`.

- [ ] **Step 3: Verify TypeScript**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 4: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add frontend/src/components/basket/BasketBuilder.tsx "frontend/src/app/[locale]/search/page.tsx"
git commit -m "feat: near-me basket filter, category chip row on search page"
```

---

## Phase 3 — Infrastructure Reliability

> All Phase 3 tasks are **[PARALLEL]** — they touch different files.

---

### Task 3.1 [PARALLEL]: Fix `_run_async` → `asyncio.run`

**Files:**
- Modify: `app/tasks.py`

- [ ] **Step 1: Replace `app/tasks.py`**

```python
import asyncio
import logging

from app.celery_app import app

logger = logging.getLogger(__name__)


@app.task(bind=True, name="app.tasks.scrape_all")
def scrape_all(self, chains=None, skip_blocked=True, workers=5):
    """Download price/store XML files for all (or selected) chains."""
    from app.scraper.mass_scraper import run_mass_scraper
    logger.info(f"[Task {self.request.id}] Starting mass scraper")
    self.update_state(state="SCRAPING")
    run_mass_scraper(chains=chains, skip_blocked=skip_blocked, workers=workers)
    logger.info(f"[Task {self.request.id}] Scraper finished")
    return {"status": "done", "task": "scrape_all"}


@app.task(bind=True, name="app.tasks.parse_all")
def parse_all(self, chains=None):
    """Parse all downloaded XML files into PostgreSQL."""
    from app.parser.mass_parser import run_mass_parser
    logger.info(f"[Task {self.request.id}] Starting mass parser")
    self.update_state(state="PARSING")
    asyncio.run(run_mass_parser(chains=chains))
    logger.info(f"[Task {self.request.id}] Parser finished")
    return {"status": "done", "task": "parse_all"}


@app.task(bind=True, name="app.tasks.scrape_and_parse")
def scrape_and_parse(self, chains=None, skip_blocked=True, workers=5):
    """Full pipeline: scrape then parse."""
    from app.scraper.mass_scraper import run_mass_scraper
    from app.parser.mass_parser import run_mass_parser
    logger.info(f"[Task {self.request.id}] Starting scrape-and-parse pipeline")
    self.update_state(state="SCRAPING")
    run_mass_scraper(chains=chains, skip_blocked=skip_blocked, workers=workers)
    self.update_state(state="PARSING")
    asyncio.run(run_mass_parser(chains=chains))
    logger.info(f"[Task {self.request.id}] Pipeline finished")
    return {"status": "done", "task": "scrape_and_parse"}


@app.task(bind=True, name="app.tasks.geocode_new")
def geocode_new(self):
    """Geocode any stores missing latitude/longitude."""
    from app.geocoder import geocode_all_stores
    logger.info(f"[Task {self.request.id}] Geocoding new stores")
    self.update_state(state="GEOCODING")
    asyncio.run(geocode_all_stores(only_missing=True))
    logger.info(f"[Task {self.request.id}] Geocoding finished")
    return {"status": "done", "task": "geocode_new"}
```

- [ ] **Step 2: Commit**

```bash
git add app/tasks.py
git commit -m "fix: replace deprecated _run_async with asyncio.run in Celery tasks"
```

---

### Task 3.2 [PARALLEL]: Split Celery beat + worker in docker-compose

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Replace the `celery` service with `celery-worker` + `celery-beat`**

In `docker-compose.yml`, replace:
```yaml
  celery:
    build: .
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://supermarket:${POSTGRES_PASSWORD:-supermarket123}@db:5432/supermarket_prices
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: celery -A app.celery_app worker --beat --loglevel=info
    volumes:
      - dumps:/app/dumps
```

With:
```yaml
  celery-worker:
    build: .
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://supermarket:${POSTGRES_PASSWORD:-supermarket123}@db:5432/supermarket_prices
      REDIS_URL: redis://redis:6379/0
      SKIP_BLOCKED_CHAINS: ${SKIP_BLOCKED_CHAINS:-true}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: celery -A app.celery_app worker --loglevel=info
    volumes:
      - dumps:/app/dumps

  celery-beat:
    build: .
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql+asyncpg://supermarket:${POSTGRES_PASSWORD:-supermarket123}@db:5432/supermarket_prices
      REDIS_URL: redis://redis:6379/0
      SKIP_BLOCKED_CHAINS: ${SKIP_BLOCKED_CHAINS:-true}
    depends_on:
      redis:
        condition: service_healthy
    command: celery -A app.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule
    volumes:
      - dumps:/app/dumps
```

Also add `SKIP_BLOCKED_CHAINS` to the `api` service environment block:
```yaml
      SKIP_BLOCKED_CHAINS: ${SKIP_BLOCKED_CHAINS:-true}
```

- [ ] **Step 2: Verify compose file is valid**

```bash
docker compose config --quiet 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "fix: separate Celery beat and worker into distinct containers"
```

---

### Task 3.3 [PARALLEL]: Real health check

**Files:**
- Modify: `main.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Health check already uses `redis` package (transitive via celery[redis]) — no new dep needed. Verify:**

```bash
python -c "import redis.asyncio; print('ok')"
```

Expected: `ok`

- [ ] **Step 2: Replace the `/health` endpoint in `main.py`**

```python
import os
from sqlalchemy import text as _sa_text
from fastapi.responses import JSONResponse

@app.get("/health")
async def health():
    db_ok = False
    redis_ok = False
    try:
        from app.db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(_sa_text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception:
        pass
    status = "ok" if (db_ok and redis_ok) else "degraded"
    return JSONResponse(
        {"status": status, "db": db_ok, "redis": redis_ok},
        status_code=200 if status == "ok" else 503,
    )
```

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: health check probes DB and Redis, returns 503 when degraded"
```

---

### Task 3.4 [PARALLEL]: Sentry error monitoring

**Files:**
- Modify: `requirements.txt`
- Modify: `main.py`
- Modify: `app/celery_app.py`

- [ ] **Step 1: Add Sentry to requirements.txt**

Append:
```
sentry-sdk[fastapi,celery]==2.4.0
```

Install:
```bash
pip install sentry-sdk[fastapi,celery]==2.4.0
```

- [ ] **Step 2: Initialize Sentry in `main.py`**

Add at the very top of `main.py`, before the `app = FastAPI(...)` call:
```python
import sentry_sdk

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=0.1,
        environment=os.getenv("DEPLOYMENT_ENV", "development"),
    )
```

- [ ] **Step 3: Initialize Sentry in `app/celery_app.py`**

Add after `load_dotenv()`:
```python
_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.05,
        environment=os.getenv("DEPLOYMENT_ENV", "development"),
    )
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt main.py app/celery_app.py
git commit -m "feat: Sentry error monitoring for FastAPI and Celery (opt-in via SENTRY_DSN)"
```

---

### Task 3.5 [PARALLEL]: VPS deployment documentation

**Files:**
- Create: `docs/deployment.md`

- [ ] **Step 1: Create `docs/deployment.md`**

```markdown
# Deployment Guide — Machirista on an Israeli VPS

## Why an Israeli VPS?

Chains Rami Levy, Osher Ad, Yohananof, Tiv Taam and several others publish prices
via FTP at `publishedprices.co.il`, which blocks non-Israeli IPs. All other chains
work from anywhere.

Recommended providers (Israeli datacenters):
- **Hetzner** — Ashkelon datacenter (cheapest, €6/mo CX22 is enough)
- **AWS** — `il-central-1` (Tel Aviv)
- **DigitalOcean** — TLV region

## Minimum Specs

- 2 vCPU, 4 GB RAM, 40 GB SSD
- Ubuntu 22.04 LTS
- Docker + Docker Compose v2 installed

## First Deploy

```bash
# 1. Clone the repo
git clone https://github.com/your-org/machirista.git && cd machirista

# 2. Copy and fill in env vars
cp .env.example .env
nano .env   # fill in POSTGRES_PASSWORD, ADMIN_API_KEY, FRONTEND_URL, etc.

# 3. Set SKIP_BLOCKED_CHAINS=false to enable Rami Levy, Osher Ad, etc.
echo "SKIP_BLOCKED_CHAINS=false" >> .env

# 4. Start all services
docker compose up -d

# 5. Run the first full scrape manually (takes 20-60 min)
docker compose exec api python -m app.scraper.mass_scraper full

# 6. Parse all downloaded files
docker compose exec api python -m app.parser.mass_parser

# 7. Geocode new stores
docker compose exec api python -m app.geocoder
```

## Outbound Firewall Requirements

The FTP chains require **outbound port 21** to be open. Check with your provider:
```bash
# Test from the VPS:
curl ftp://publishedprices.co.il --connect-timeout 5
# Should return an FTP banner, not "Connection refused"
```

Some providers (Hetzner included) have port 21 open by default.

## Updating

```bash
git pull
docker compose build
docker compose up -d
```

## Checking Logs

```bash
docker compose logs -f celery-worker   # scrape/parse progress
docker compose logs -f celery-beat     # schedule firing
docker compose logs -f api             # API errors
```

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | PostgreSQL async URL |
| `REDIS_URL` | yes | Redis URL |
| `POSTGRES_PASSWORD` | yes | DB password |
| `ADMIN_API_KEY` | yes | Protects /tasks/* and /admin/* |
| `FRONTEND_URL` | yes | CORS allowlist (e.g. https://machirista.co.il) |
| `SKIP_BLOCKED_CHAINS` | no | Set `false` on Israeli VPS. Default: `true` |
| `SENTRY_DSN` | no | Sentry project DSN. Empty = disabled |
| `ADMIN_PASSWORD` | no | Frontend admin dashboard password |
| `NEXT_PUBLIC_ADMIN_API_KEY` | no | Same as ADMIN_API_KEY, used by admin frontend |
```

- [ ] **Step 2: Commit**

```bash
git add docs/deployment.md
git commit -m "docs: VPS deployment guide with Israeli datacenter instructions"
```

---

## Phase 4 — Polish & Growth

> All Phase 4 tasks are **[PARALLEL]**.

---

### Task 4.1 [PARALLEL]: Basket localStorage expiry

**Files:**
- Modify: `frontend/src/lib/basket-store.ts`

- [ ] **Step 1: Replace `basket-store.ts`**

```typescript
"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

export interface BasketItem {
  barcode: string;
  name: string;
  brand?: string;
  imageUrl?: string;
  quantity: number;
}

interface BasketStore {
  items: BasketItem[];
  savedAt: number;
  addItem: (item: Omit<BasketItem, "quantity">) => void;
  removeItem: (barcode: string) => void;
  updateQuantity: (barcode: string, quantity: number) => void;
  clearBasket: () => void;
}

export const useBasket = create<BasketStore>()(
  persist(
    (set) => ({
      items: [],
      savedAt: Date.now(),
      addItem: (item) =>
        set((state) => {
          const existing = state.items.find((i) => i.barcode === item.barcode);
          if (existing) {
            return {
              items: state.items.map((i) =>
                i.barcode === item.barcode ? { ...i, quantity: i.quantity + 1 } : i
              ),
              savedAt: Date.now(),
            };
          }
          return { items: [...state.items, { ...item, quantity: 1 }], savedAt: Date.now() };
        }),
      removeItem: (barcode) =>
        set((state) => ({
          items: state.items.filter((i) => i.barcode !== barcode),
          savedAt: Date.now(),
        })),
      updateQuantity: (barcode, quantity) =>
        set((state) => ({
          items:
            quantity <= 0
              ? state.items.filter((i) => i.barcode !== barcode)
              : state.items.map((i) => (i.barcode === barcode ? { ...i, quantity } : i)),
          savedAt: Date.now(),
        })),
      clearBasket: () => set({ items: [], savedAt: Date.now() }),
    }),
    {
      name: "machirista-basket",
      onRehydrateStorage: () => (state) => {
        if (state && Date.now() - (state.savedAt ?? 0) > SEVEN_DAYS_MS) {
          state.items = [];
          state.savedAt = Date.now();
        }
      },
    }
  )
);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/basket-store.ts
git commit -m "feat: basket localStorage expires after 7 days"
```

---

### Task 4.2 [PARALLEL]: Shareable basket URL

**Files:**
- Create: `frontend/src/lib/share.ts`
- Modify: `frontend/src/components/basket/BasketBuilder.tsx`

- [ ] **Step 1: Create `frontend/src/lib/share.ts`**

```typescript
import type { BasketItem } from "./basket-store";

type Minimal = { b: string; q: number };

export function encodeBasket(items: BasketItem[]): string {
  const minimal: Minimal[] = items.map((i) => ({ b: i.barcode, q: i.quantity }));
  return btoa(encodeURIComponent(JSON.stringify(minimal)));
}

export function decodeBasket(encoded: string): Array<{ barcode: string; quantity: number }> | null {
  try {
    const json = decodeURIComponent(atob(encoded));
    const parsed = JSON.parse(json) as Minimal[];
    if (!Array.isArray(parsed)) return null;
    return parsed.map((i) => ({ barcode: i.b, quantity: i.q }));
  } catch {
    return null;
  }
}

export function toShareUrl(items: BasketItem[]): string {
  return `${window.location.origin}/he/?b=${encodeBasket(items)}`;
}
```

- [ ] **Step 2: Add share button + URL hydration to `BasketBuilder.tsx`**

Add imports at top:
```tsx
import { useSearchParams } from "next/navigation";
import { toShareUrl, decodeBasket } from "@/lib/share";
```

Add state and hydration inside the component:
```tsx
  const searchParams = useSearchParams();
  const [copied, setCopied] = useState(false);

  // Hydrate basket from shared URL on mount
  useEffect(() => {
    const b = searchParams.get("b");
    if (b && items.length === 0) {
      const decoded = decodeBasket(b);
      if (decoded) {
        decoded.forEach(({ barcode, quantity }) => {
          // Add placeholder items; real names load when compare runs
          for (let i = 0; i < quantity; i++) {
            addItem({ barcode, name: barcode });
          }
        });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleShare = async () => {
    const url = toShareUrl(items);
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
```

Add share button inside the basket items block, next to the clear button:
```tsx
              <button onClick={handleShare}
                className="text-[11px] font-semibold text-gray-400 hover:text-gray-700 transition-colors uppercase tracking-wide">
                {copied ? (isRtl ? "הועתק!" : "Copied!") : (isRtl ? "שתף" : "Share")}
              </button>
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend && npx tsc --noEmit 2>&1 | grep "share\|BasketBuilder" | head -10
```

- [ ] **Step 4: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add frontend/src/lib/share.ts frontend/src/components/basket/BasketBuilder.tsx
git commit -m "feat: shareable basket URL via base64 encoded query param"
```

---

### Task 4.3 [PARALLEL]: Admin dashboard frontend

**Files:**
- Create: `frontend/src/app/[locale]/admin/page.tsx`

- [ ] **Step 1: Create `frontend/src/app/[locale]/admin/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { getChainStats } from "@/lib/api";

const ADMIN_PASSWORD = process.env.NEXT_PUBLIC_ADMIN_PASSWORD ?? "";
const ADMIN_API_KEY = process.env.NEXT_PUBLIC_ADMIN_API_KEY ?? "";

interface ChainStat {
  chain_name: string;
  last_scraped?: string;
  products_parsed: number;
  stores_total: number;
  stores_geocoded: number;
  geocoding_pct: number;
}

function relTime(iso?: string) {
  if (!iso) return "—";
  const h = Math.floor((Date.now() - new Date(iso).getTime()) / 3600000);
  if (h < 1) return "< 1h ago";
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function AdminPage() {
  const [authed, setAuthed] = useState(false);
  const [pw, setPw] = useState("");
  const [stats, setStats] = useState<ChainStat[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const saved = sessionStorage.getItem("admin_authed");
    if (saved === "1") setAuthed(true);
  }, []);

  useEffect(() => {
    if (!authed) return;
    setLoading(true);
    getChainStats(ADMIN_API_KEY)
      .then((data) => setStats(data as ChainStat[]))
      .finally(() => setLoading(false));
  }, [authed]);

  const handleLogin = () => {
    if (pw === ADMIN_PASSWORD) {
      sessionStorage.setItem("admin_authed", "1");
      setAuthed(true);
    }
  };

  if (!authed) {
    return (
      <div className="max-w-sm mx-auto px-5 py-20">
        <h1 className="text-xl font-bold text-gray-900 mb-6">Admin</h1>
        <input
          type="password"
          value={pw}
          onChange={(e) => setPw(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          placeholder="Password"
          className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm mb-3 outline-none focus:border-brand-400"
        />
        <button onClick={handleLogin}
          className="w-full bg-brand-600 text-white rounded-xl py-2.5 text-sm font-semibold hover:bg-brand-700 transition-colors">
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-5 py-10">
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Chain Status</h1>
        <button onClick={() => { sessionStorage.removeItem("admin_authed"); setAuthed(false); }}
          className="text-xs text-gray-400 hover:text-gray-600">Logout</button>
      </div>

      {loading ? (
        <p className="text-gray-400 text-sm">Loading...</p>
      ) : (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                {["Chain", "Last Scraped", "Products", "Stores", "Geocoded"].map((h) => (
                  <th key={h} className="px-4 py-2.5 text-left text-[10px] font-semibold tracking-widest uppercase text-gray-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {stats.map((s) => (
                <tr key={s.chain_name} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-3 font-medium text-gray-900">{s.chain_name}</td>
                  <td className="px-4 py-3 text-gray-500 font-mono text-xs">{relTime(s.last_scraped)}</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-gray-700">{s.products_parsed.toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono tabular-nums text-gray-700">{s.stores_total}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${s.geocoding_pct > 80 ? "bg-green-400" : s.geocoding_pct > 50 ? "bg-amber-400" : "bg-red-400"}`}
                          style={{ width: `${s.geocoding_pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 w-10 text-end">{s.geocoding_pct}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add `NEXT_PUBLIC_ADMIN_PASSWORD` to frontend env**

In `frontend/.env.local` (create if missing):
```
NEXT_PUBLIC_ADMIN_PASSWORD=change-me
NEXT_PUBLIC_ADMIN_API_KEY=change-me
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd /Users/liabenyehonatan/supermarket-prices/frontend && npx tsc --noEmit 2>&1 | grep "admin" | head -10
```

- [ ] **Step 4: Commit**

```bash
cd /Users/liabenyehonatan/supermarket-prices
git add "frontend/src/app/[locale]/admin/page.tsx" frontend/.env.local
git commit -m "feat: admin dashboard — chain stats table with geocoding progress bars"
```

---

## Self-Review Checklist

### Spec coverage
| Spec item | Task |
|---|---|
| 1.1 API key auth | Task 1.1 |
| 1.2 CORS from env | Task 1.1 |
| 1.3 nginx.conf | Task 1.2 |
| 1.4 Basket ranking | Task 1.3 |
| 1.5 Transfer basket | Task 1.4 |
| 1.6 Remove dead Vite | Task 1.5 |
| 2.1 Promotions API + UI | Tasks 2.0, 2.2, 2.9 |
| 2.2 Price history + sparkline | Tasks 2.0, 2.3, 2.9 |
| 2.3 Stats + freshness | Tasks 2.0, 2.1, 2.7, 2.9 |
| 2.4 Fuzzy search | Task 2.1 |
| 2.5 Geocoder in pipeline | Task 2.5 |
| 2.6 Near-me filter | Tasks 2.4, 2.10 |
| 3.1 Fix _run_async | Task 3.1 |
| 3.2 Celery beat/worker split | Task 3.2 |
| 3.3 Real health check | Task 3.3 |
| 3.4 SKIP_BLOCKED_CHAINS | Task 2.5 (celery_app.py) + Task 3.2 |
| 3.5 Sentry | Task 3.4 |
| 4.1 Shareable basket | Task 4.2 |
| 4.2 Category browsing | Tasks 2.1, 2.10 |
| 4.3 Admin dashboard | Tasks 2.6, 4.3 |
| 4.4 Basket expiry | Task 4.1 |
| 4.5 StatsBar live | Task 2.7 |
