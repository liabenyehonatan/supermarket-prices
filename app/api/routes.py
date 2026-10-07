# app/api/routes.py

import logging
from decimal import Decimal
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.db.models import Product, Price, Store, Chain
from app.api.schemas import (
    ProductSearchResult,
    ProductCompareResponse,
    PriceAtStore,
    BasketItem,
    BasketCompareResponse,
    BasketStoreTotal,
    StoreResponse,
    ChainResponse,
)

logger = logging.getLogger(__name__)

# APIRouter is like a mini FastAPI app.
# We use it to group related endpoints together.
# The prefix means all routes here start with /api/v1
router = APIRouter(prefix="/api/v1")


# ─── Endpoint 1: Search Products ─────────────────────────────────────────────

@router.get(
    "/products/search",
    response_model=List[ProductSearchResult],
    summary="Search products by name or barcode",
)
async def search_products(
    # Query parameters — these come from the URL like:
    # /products/search?q=טבסקו&limit=10
    q: str = Query(..., min_length=1, description="Product name or barcode to search for"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip (for paging)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for products by name (Hebrew supported) or exact barcode.

    Examples:
    - /api/v1/products/search?q=טבסקו
    - /api/v1/products/search?q=7290000066885
    - /api/v1/products/search?q=חלב&limit=20&offset=20  (second page)
    """

    # Check if the query looks like a barcode (all digits)
    is_barcode = q.strip().isdigit()

    # Subquery: count current prices per product (proxy for popularity)
    store_count_sq = (
        select(Price.product_id, func.count(Price.id).label("store_count"))
        .where(Price.is_current == True)
        .group_by(Price.product_id)
        .subquery()
    )

    if is_barcode:
        result = await db.execute(
            select(Product).where(Product.barcode == q.strip()).limit(limit)
        )
        products = result.scalars().all()
    else:
        from sqlalchemy import case as sa_case
        # Any word may match (like Shufersal's own search), in any order.
        # Ranking: names that contain more of the query's words come first,
        # then names starting with the full query, then popularity.
        words = q.split()
        if not words:
            return []
        word_hits = [
            sa_case((Product.name.icontains(w, autoescape=True), 1), else_=0)
            for w in words
        ]
        words_matched = sum(word_hits)
        prefix_bonus = sa_case((Product.name.ilike(f"{q}%"), 1), else_=0)
        exact_q = (
            select(Product, func.coalesce(store_count_sq.c.store_count, 0).label("sc"))
            .outerjoin(store_count_sq, Product.id == store_count_sq.c.product_id)
            .where(or_(*[Product.name.icontains(w, autoescape=True) for w in words]))
            .order_by(
                words_matched.desc(),
                prefix_bonus.desc(),
                func.coalesce(store_count_sq.c.store_count, 0).desc(),
                Product.id,  # stable order so pages don't overlap
            )
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(exact_q)
        rows = result.all()
        products = [r[0] for r in rows]

        if not products and offset == 0:
            # Fuzzy fallback (first page only — later pages would just append noise) via pg_trgm — handles typos like "גבימה" → "גבינה"
            fuzzy_q = (
                select(Product, func.coalesce(store_count_sq.c.store_count, 0).label("sc"))
                .outerjoin(store_count_sq, Product.id == store_count_sq.c.product_id)
                .where(func.word_similarity(q, Product.name) > 0.2)
                .order_by(
                    func.word_similarity(q, Product.name).desc(),
                    func.coalesce(store_count_sq.c.store_count, 0).desc(),
                    Product.id,
                )
                .offset(offset)
                .limit(limit)
            )
            result = await db.execute(fuzzy_q)
            products = [r[0] for r in result.all()]

    return products


# ─── Endpoint 2: Compare Product Prices ──────────────────────────────────────

@router.get(
    "/products/{barcode}/compare",
    response_model=ProductCompareResponse,
    summary="Compare prices of one product across all stores",
)
async def compare_product_prices(
    barcode: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the price of a specific product in every store we have data for.
    Results are sorted cheapest first.

    Example:
    - /api/v1/products/11210000094/compare
    """

    # Step 1: Find the product
    result = await db.execute(
        select(Product).where(Product.barcode == barcode)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"Product with barcode {barcode} not found"
        )

    # Step 2: Get all current prices for this product
    # We join Price → Store → Chain to get all info in one query
    prices_query = (
        select(Price, Store, Chain)
        .join(Store, Price.store_id == Store.id)
        .join(Chain, Store.chain_id == Chain.id)
        .where(
            Price.product_id == product.id,
            Price.is_current == True,
            ~Store.name.ilike("%סיטונ%"),  # exclude wholesale stores
        )
        .order_by(Price.price.asc())  # Cheapest first
    )

    prices_result = await db.execute(prices_query)
    rows = prices_result.all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No prices found for barcode {barcode}"
        )

    # Step 3: Build the response
    price_list = []
    for price, store, chain in rows:
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
        ))

    cheapest = price_list[0].price
    most_expensive = price_list[-1].price

    return ProductCompareResponse(
        product=product,
        prices=price_list,
        cheapest_price=cheapest,
        most_expensive_price=most_expensive,
        price_difference=most_expensive - cheapest,
    )


# ─── Endpoint: List cities ───────────────────────────────────────────────────

@router.get(
    "/stores/cities",
    response_model=List[str],
    summary="Return all distinct store cities",
)
async def list_cities(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Store.city)
        .where(Store.city.isnot(None), Store.city != "")
        .distinct()
        .order_by(Store.city)
    )
    return [row[0] for row in result.all()]


# ─── Endpoint: Product image (via Shufersal CDN) ─────────────────────────────

SHUFERSAL_SEARCH = "https://www.shufersal.co.il/online/he/search/results"
SHUFERSAL_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

@router.get("/products/{barcode}/image", summary="Redirect to product image")
async def get_product_image(barcode: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.barcode == barcode))
    product = result.scalar_one_or_none()

    if product and product.image_url:
        return RedirectResponse(product.image_url, status_code=302)

    def _names_similar(our_name: str, their_name: str) -> bool:
        our_words = set(our_name.split())
        their_words = set(their_name.split())
        if not our_words:
            return False
        return len(our_words & their_words) / len(our_words) >= 0.6

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                SHUFERSAL_SEARCH,
                params={"q": barcode, "format": "json"},
                headers=SHUFERSAL_HEADERS,
            )
            results = resp.json().get("results", [])

            if not results and product:
                resp2 = await client.get(
                    SHUFERSAL_SEARCH,
                    params={"q": product.name, "format": "json"},
                    headers=SHUFERSAL_HEADERS,
                )
                name_results = resp2.json().get("results", [])
                results = [
                    r for r in name_results
                    if _names_similar(product.name, r.get("name", ""))
                ]

        image_url = results[0].get("baseProductImageMedium") if results else None
    except Exception:
        image_url = None

    if image_url and product:
        product.image_url = image_url
        await db.commit()
        return RedirectResponse(image_url, status_code=302)

    raise HTTPException(status_code=404, detail="No image found")


# ─── Endpoint 3: Basket Comparison ───────────────────────────────────────────

@router.post(
    "/basket/compare",
    response_model=BasketCompareResponse,
    summary="Compare total basket price across all stores",
)
async def compare_basket(
    items: List[BasketItem],
    city: Optional[str] = Query(None, description="Only stores whose city contains this text"),
    chain: Optional[str] = Query(None, description="Only stores of this chain (exact name)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Given a list of products (barcodes + quantities), calculate the
    total cost at every store and sort from cheapest to most expensive.

    This is the core feature of the app — basket comparison!

    Example request body:
    [
        {"barcode": "11210000094", "quantity": 2},
        {"barcode": "7290000066885", "quantity": 1}
    ]

    Optional query params narrow the stores compared, matching the
    filters of the product compare page: ?city=הרצליה&chain=שופרסל
    """

    if not items:
        raise HTTPException(status_code=400, detail="Basket cannot be empty")

    # Step 1: Get all barcodes from the basket
    barcodes = [item.barcode for item in items]
    quantity_map = {item.barcode: item.quantity for item in items}

    # Step 2: Find all products in the basket
    products_result = await db.execute(
        select(Product).where(Product.barcode.in_(barcodes))
    )
    products = {p.barcode: p for p in products_result.scalars().all()}

    # Step 3: Get all current prices for all basket products
    # This is ONE query that fetches everything we need
    prices_query = (
        select(Price, Product, Store, Chain)
        .join(Product, Price.product_id == Product.id)
        .join(Store, Price.store_id == Store.id)
        .join(Chain, Store.chain_id == Chain.id)
        .where(
            Product.barcode.in_(barcodes),
            Price.is_current == True,
            ~Store.name.ilike("%סיטונ%"),  # exclude wholesale stores
        )
    )
    if city and city.strip():
        # Same "contains" match the product page uses
        prices_query = prices_query.where(Store.city.icontains(city.strip(), autoescape=True))
    if chain and chain.strip():
        prices_query = prices_query.where(Chain.name == chain.strip())

    prices_result = await db.execute(prices_query)
    all_price_rows = prices_result.all()

    # Step 4: Group prices by store
    # store_id → {barcode → price_info}
    store_prices: dict = {}
    store_objects: dict = {}
    chain_objects: dict = {}

    for price, product, store, chain in all_price_rows:
        if store.id not in store_prices:
            store_prices[store.id] = {}
            store_objects[store.id] = store
            chain_objects[store.id] = chain

        store_prices[store.id][product.barcode] = {
            "product_name": product.name,
            "barcode": product.barcode,
            "unit_price": price.price,
            "quantity": quantity_map.get(product.barcode, 1),
            "line_total": price.price * quantity_map.get(product.barcode, 1),
        }

    # Step 5: Calculate total per store
    store_totals = []

    for store_id, barcode_prices in store_prices.items():
        store = store_objects[store_id]
        chain = chain_objects[store_id]

        # Calculate total for items this store HAS
        total = sum(
            info["line_total"]
            for info in barcode_prices.values()
        )

        items_found = len(barcode_prices)
        items_missing = len(barcodes) - items_found

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
            item_prices=list(barcode_prices.values()),
        ))

    # Step 6: Sort — complete baskets first, then by price ascending
    store_totals.sort(key=lambda x: (x.items_missing, x.total_price))

    # Calculate max savings among complete-basket stores only
    complete = [s for s in store_totals if s.items_missing == 0]
    if len(complete) >= 2:
        max_savings = complete[-1].total_price - complete[0].total_price
        cheapest_store = complete[0].store.name
    elif store_totals:
        max_savings = Decimal("0")
        cheapest_store = store_totals[0].store.name
    else:
        max_savings = Decimal("0")
        cheapest_store = None

    return BasketCompareResponse(
        stores=store_totals,
        total_items_requested=len(barcodes),
        cheapest_store=cheapest_store,
        max_savings=max_savings,
    )