# app/api/routes.py

import logging
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, and_
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
    db: AsyncSession = Depends(get_db),
):
    """
    Search for products by name (Hebrew supported) or exact barcode.

    Examples:
    - /api/v1/products/search?q=טבסקו
    - /api/v1/products/search?q=7290000066885
    """

    # Check if the query looks like a barcode (all digits)
    is_barcode = q.strip().isdigit()

    if is_barcode:
        # Exact barcode match
        query = select(Product).where(
            Product.barcode == q.strip()
        ).limit(limit)
    else:
        # Hebrew text search using ILIKE (case-insensitive LIKE)
        # % means "anything before or after"
        # So %טבסקו% matches "רוטב טבסקו 60 מ"ל"
        query = select(Product).where(
            Product.name.ilike(f"%{q}%")
        ).limit(limit)

    result = await db.execute(query)
    products = result.scalars().all()

    if not products:
        # Return empty list, not an error
        return []

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


# ─── Endpoint 3: Basket Comparison ───────────────────────────────────────────

@router.post(
    "/basket/compare",
    response_model=BasketCompareResponse,
    summary="Compare total basket price across all stores",
)
async def compare_basket(
    items: List[BasketItem],
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
        )
    )

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

    # Step 6: Sort by total price — cheapest first
    store_totals.sort(key=lambda x: x.total_price)

    # Calculate max savings
    if len(store_totals) >= 2:
        max_savings = store_totals[-1].total_price - store_totals[0].total_price
        cheapest_store = store_totals[0].store.name
    else:
        max_savings = Decimal("0")
        cheapest_store = store_totals[0].store.name if store_totals else None

    return BasketCompareResponse(
        stores=store_totals,
        total_items_requested=len(barcodes),
        cheapest_store=cheapest_store,
        max_savings=max_savings,
    )