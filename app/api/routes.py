# app/api/routes.py

import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Annotated, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select, func, and_, or_, text, literal, update
from sqlalchemy import column as sa_column, table as sa_table
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.database import get_db
from app.basket_promos import StorePromo, price_store
from app.chains import display_chain_name, display_chain_name_sql
from app.images import ImageLookupError, is_allowed_image_url
from app.images import lookup_image_url as _lookup_image_url
from app.db.models import Product, Price, Promotion, Store, Chain
from app.api.schemas import (
    ChainListItem,
    ProductSearchResult,
    ProductCompareResponse,
    PriceAtStore,
    PromoInfo,
    CheapestPriceRequest,
    BasketItem,
    BasketCompareResponse,
    BasketStoreTotal,
    StoreResponse,
    ChainResponse,
    StatsResponse,
    ExampleComparison,
    UnitPriceInfo,
)

logger = logging.getLogger(__name__)

# APIRouter is like a mini FastAPI app.
# We use it to group related endpoints together.
# The prefix means all routes here start with /api/v1
router = APIRouter(prefix="/api/v1")


# Barcodes shorter than this are a chain's own item numbers (the same number is a different product at
# another chain), so they are never compared across chains.
MIN_BARCODE_LEN = 7
MAX_SEARCH_WORDS = 6


def _real_barcode():
    return func.length(Product.barcode) >= MIN_BARCODE_LEN


def _not_wholesale():
    """Wholesale stores are not for shoppers. A store without a name is kept (it is not wholesale)."""
    return or_(Store.name.is_(None), ~Store.name.ilike("%סיטונ%"))


# ─── Endpoint 1: Search Products ─────────────────────────────────────────────

@router.get(
    "/products/search",
    response_model=List[ProductSearchResult],
    summary="Search products by name or barcode",
)
async def search_products(
    # Query parameters — these come from the URL like:
    # /products/search?q=טבסקו&limit=10
    q: str = Query(..., min_length=1, max_length=100, description="Product name or barcode to search for"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, le=10000, description="Number of results to skip (for paging)"),
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
    # Precomputed by the worker after each cycle (a live GROUP BY over every current price
    # took ~9 s per search once all chains were loaded).
    store_count_sq = (
        sa_table("product_store_counts", sa_column("product_id"), sa_column("store_count")).alias("store_count_sq")
    )

    if is_barcode:
        result = await db.execute(
            select(Product).where(Product.barcode == q.strip(), _real_barcode()).limit(limit)
        )
        products = result.scalars().all()
    else:
        from sqlalchemy import case as sa_case
        # Any word may match (like Shufersal's own search), in any order.
        # Ranking: names that contain more of the query's words come first,
        # then names starting with the full query, then popularity.
        # A bounded number of meaningful words: thousands of one-letter terms would scan every product.
        words = [w for w in q.split() if len(w) >= 2][:MAX_SEARCH_WORDS]
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
            .where(or_(*[Product.name.icontains(w, autoescape=True) for w in words]), _real_barcode())
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
            # `<%` can use the trigram index (word_similarity(...) > x cannot and scanned every product);
            # the threshold is set for this transaction only.
            await db.execute(text("SET LOCAL pg_trgm.word_similarity_threshold = 0.3"))
            fuzzy_q = (
                select(Product, func.coalesce(store_count_sq.c.store_count, 0).label("sc"))
                .outerjoin(store_count_sq, Product.id == store_count_sq.c.product_id)
                .where(literal(" ".join(words)).op("<%")(Product.name), _real_barcode())
                .order_by(
                    func.word_similarity(" ".join(words), Product.name).desc(),
                    func.coalesce(store_count_sq.c.store_count, 0).desc(),
                    Product.id,
                )
                .offset(offset)
                .limit(limit)
            )
            result = await db.execute(fuzzy_q)
            products = [r[0] for r in result.all()]

    return products


MAX_PROMOS_PER_STORE = 3


PROMO_FRESH_DAYS = 7      # a store's promotions count in the basket only if its promotion file was loaded this recently


def _running_now():
    """The promotion is inside its dates now (chains publish Israel local time without a zone)."""
    now_il = func.timezone("Asia/Jerusalem", func.now())
    return and_(
        Promotion.is_active,
        or_(Promotion.start_date.is_(None), Promotion.start_date <= now_il),
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now_il),
    )


async def _running_promotions(db: AsyncSession, product_id: int, store_ids: list[int]) -> dict[int, list[PromoInfo]]:
    """Promotions running now per store, soonest end first."""
    rows = await db.execute(
        select(Promotion.store_id, Promotion.description, Promotion.min_qty, Promotion.end_date)
        .where(
            Promotion.product_id == product_id,
            Promotion.store_id.in_(store_ids),
            _running_now(),
        )
        .order_by(Promotion.store_id, Promotion.end_date.asc().nulls_last(), Promotion.promotion_id)
    )
    by_store: dict[int, list[PromoInfo]] = {}
    for store_id, description, min_qty, end_date in rows.all():
        bucket = by_store.setdefault(store_id, [])
        if len(bucket) < MAX_PROMOS_PER_STORE:
            bucket.append(PromoInfo(description=description or "", min_qty=min_qty, ends_at=end_date))
    return by_store


async def _basket_promotions(db: AsyncSession, product_ids: list[int], store_ids: list[int]) -> dict[int, list[StorePromo]]:
    """Promotions safe to price a basket with, running now, per store: each with the basket products it covers there."""
    if not product_ids or not store_ids:
        return {}
    rows = await db.execute(
        select(
            Promotion.store_id, Promotion.product_id, Promotion.promotion_id, Promotion.description,
            Promotion.min_qty, Promotion.discounted_price, Promotion.max_qty, Promotion.price_is_total,
        ).where(
            Promotion.product_id.in_(product_ids),
            Promotion.store_id.in_(store_ids),
            Promotion.basket_eligible,
            Promotion.min_qty.is_not(None),
            Promotion.discounted_price.is_not(None),
            _running_now(),
        )
    )
    heads: dict[tuple[int, str], tuple] = {}
    members: dict[tuple[int, str], set[int]] = {}
    for store_id, product_id, promotion_id, description, min_qty, price, max_qty, price_is_total in rows.all():
        key = (store_id, promotion_id)
        heads.setdefault(key, (description or "", min_qty, price, max_qty, price_is_total))
        members.setdefault(key, set()).add(product_id)
    by_store: dict[int, list[StorePromo]] = {}
    for (store_id, promotion_id), (description, min_qty, price, max_qty, price_is_total) in heads.items():
        by_store.setdefault(store_id, []).append(
            StorePromo(promotion_id, description, min_qty, price, max_qty, price_is_total,
                       frozenset(members[(store_id, promotion_id)])))
    return by_store


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
        select(Product).where(Product.barcode == barcode, _real_barcode())
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
            Price.price > 0,  # a 0 price means "none", never the cheapest
            _not_wholesale(),  # exclude wholesale stores
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

    promos = await _running_promotions(db, product.id, [store.id for _, store, _ in rows])

    # Step 3: Build the response
    price_list = []
    for price, store, chain in rows:
        price_list.append(PriceAtStore(
            store_id=store.id,
            store_name=store.name,
            store_city=store.city,
            store_address=store.address,
            chain_name=display_chain_name(chain.name, store.name),
            price=price.price,
            unit_price=price.unit_price,
            price_updated_at=price.price_updated_at,
            # Confirmed when the store's last complete file was loaded (or when this very row was written).
            scraped_at=max(filter(None, (price.scraped_at, store.last_full_at)), default=None),
            latitude=store.latitude,
            longitude=store.longitude,
            delivery_url=store.delivery_url,
            promotions=promos.get(store.id, []),
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


# ─── Endpoint: Cheapest price for many products at once ─────────────────────

@router.post(
    "/products/cheapest-batch",
    response_model=dict[str, Decimal],
    summary="Cheapest current price for a list of barcodes, in one request",
)
async def cheapest_prices_batch(
    payload: CheapestPriceRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Given a list of barcodes, return the cheapest current price for each.

    Replaces calling /products/{barcode}/compare once per result on a search
    page (N requests) with a single query. A barcode with no current price is
    left out of the response.

    Example:
    - POST /api/v1/products/cheapest-batch  {"barcodes": ["729...", "729..."]}
    """
    barcodes = [b for b in payload.barcodes if b]
    if not barcodes:
        return {}

    rows = await db.execute(
        select(Product.barcode, func.min(Price.price))
        .join(Price, Price.product_id == Product.id)
        .join(Store, Price.store_id == Store.id)
        .where(
            Product.barcode.in_(barcodes),
            _real_barcode(),
            Price.is_current == True,
            Price.price > 0,  # a 0 price means "none", never the cheapest
            _not_wholesale(),  # exclude wholesale stores, same as /compare
        )
        .group_by(Product.barcode)
    )
    return {barcode: price for barcode, price in rows.all()}


# ─── Endpoint: Cheapest unit price for many products at once ────────────────

@router.post(
    "/products/unit-prices-batch",
    response_model=dict[str, UnitPriceInfo],
    summary="Cheapest current price per unit (per 100 g, per litre…) for a list of barcodes",
)
async def unit_prices_batch(
    payload: CheapestPriceRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    For ordering different pack sizes of similar products by what a unit really costs.
    A barcode with no unit price on record is left out. Prices are per the product's own
    `unit_of_measure`, so only compare values that share the same unit.
    """
    barcodes = [b for b in payload.barcodes if b]
    if not barcodes:
        return {}

    rows = await db.execute(
        select(Product.barcode, Product.unit_of_measure, func.min(Price.unit_price))
        .join(Price, Price.product_id == Product.id)
        .join(Store, Price.store_id == Store.id)
        .where(
            Product.barcode.in_(barcodes),
            _real_barcode(),
            Price.is_current == True,
            Price.price > 0,  # a 0 price means "none", never the cheapest
            Price.unit_price.isnot(None),
            Price.unit_price > 0,
            _not_wholesale(),  # exclude wholesale stores, same as /compare
        )
        .group_by(Product.barcode, Product.unit_of_measure)
    )
    return {
        barcode: UnitPriceInfo(unit_price=unit_price, unit=unit)
        for barcode, unit, unit_price in rows.all()
    }


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


# ─── Endpoint: Overall data stats (for the home page trust line) ─────────────

_STATS_TTL_SECONDS = 600
_stats_cache: tuple[float, StatsResponse] | None = None


@router.get(
    "/chains",
    response_model=List[ChainListItem],
    summary="Chains we hold prices for (the list the app filters by), biggest first",
)
async def list_chains(db: AsyncSession = Depends(get_db)):
    name = display_chain_name_sql()
    rows = await db.execute(
        select(name.label("name"), func.count(Store.id).label("stores"))
        .select_from(Store)
        .join(Chain, Chain.id == Store.chain_id)
        .group_by(name)
        .order_by(func.count(Store.id).desc(), name)
    )
    return [ChainListItem(name=r.name, stores=r.stores) for r in rows.all()]


@router.get(
    "/location/city",
    summary="The city nearest to a position, from the stores we hold (no third-party lookup)",
)
async def city_near(
    lat: float = Query(..., ge=29.0, le=34.0),
    lng: float = Query(..., ge=34.0, le=36.0),
    db: AsyncSession = Depends(get_db),
):
    """Used to suggest a city filter from the browser's position. Answers with the city of the
    closest located store within 25 km, or null. The position is not stored or sent anywhere else."""
    row = (await db.execute(
        text(
            """
            SELECT city, sqrt(power(latitude - :lat, 2) + power((longitude - :lng) * 0.85, 2)) * 111 AS km
              FROM stores
             WHERE latitude IS NOT NULL AND city IS NOT NULL AND city <> '' AND city !~ '^[0-9]+$'
             ORDER BY power(latitude - :lat, 2) + power((longitude - :lng) * 0.85, 2)
             LIMIT 1
            """
        ),
        {"lat": lat, "lng": lng},
    )).first()
    if row is None or row.km > 25:
        return {"city": None}
    return {"city": row.city, "km": round(row.km, 1)}


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="How much data we hold and when prices were last refreshed",
)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Counts and the latest scrape time. Cached for a few minutes: the numbers move at most daily."""
    global _stats_cache
    now = time.monotonic()
    if _stats_cache and now - _stats_cache[0] < _STATS_TTL_SECONDS:
        return _stats_cache[1]

    chains = (await db.execute(select(func.count(func.distinct(Store.chain_id))))).scalar_one()
    stores = (await db.execute(select(func.count(Store.id)))).scalar_one()
    products = (await db.execute(select(func.count(Product.id)))).scalar_one()
    last_updated = (await db.execute(select(func.max(Store.last_full_at)))).scalar_one()
    if last_updated is None:
        last_updated = (await db.execute(select(func.max(Price.scraped_at)))).scalar_one()

    stats = StatsResponse(chains=chains, stores=stores, products=products, last_updated=last_updated)
    _stats_cache = (now, stats)
    return stats


# ─── Endpoint: Example comparisons (home page) ───────────────────────────────

_EXAMPLES_TTL_SECONDS = 3600
_examples_cache: tuple[float, list[ExampleComparison]] | None = None


@router.get(
    "/products/examples",
    response_model=List[ExampleComparison],
    summary="A few widely stocked products with a real price gap",
)
async def example_comparisons(
    limit: int = Query(3, ge=1, le=6),
    db: AsyncSession = Depends(get_db),
):
    """
    Shows what the app does with real numbers: products sold in many stores whose
    cheapest and priciest current prices differ noticeably. "Widely stocked" stands in
    for "popular". Cached for an hour.
    """
    global _examples_cache
    now = time.monotonic()
    if _examples_cache and now - _examples_cache[0] < _EXAMPLES_TTL_SECONDS:
        return _examples_cache[1][:limit]

    # Straight from the precomputed view (refreshed after every cycle): widely stocked products that
    # already have a picture. Short codes are chain-internal item numbers, and a spread above 8x is
    # almost always a placeholder price (a coupon at 0.01), so neither makes a trustworthy example.
    candidates = (await db.execute(text(
        """
        SELECT v.product_id, v.store_count AS n, v.min_price AS lo, v.max_price AS hi
          FROM product_store_counts v JOIN products p ON p.id = v.product_id
         WHERE v.store_count >= 20 AND p.image_url IS NOT NULL AND length(p.barcode) >= 7
           AND v.min_price >= 0.5 AND v.max_price - v.min_price >= 0.5
           AND v.max_price / v.min_price BETWEEN 1.1 AND 8
         ORDER BY v.store_count DESC
         LIMIT 80
        """
    ))).all()
    picked = list(candidates)

    async def extreme(product_id: int, ascending: bool):
        order = Price.price.asc() if ascending else Price.price.desc()
        row = (await db.execute(
            select(Price.price, display_chain_name_sql())
            .join(Store, Store.id == Price.store_id)
            .join(Chain, Chain.id == Store.chain_id)
            .where(Price.product_id == product_id, Price.is_current, Price.price > 0)
            .order_by(order)
            .limit(1)
        )).first()
        return row

    seen_lines: set[str] = set()   # first word of the name, so three flavours of one snack don't fill the row
    results: list[ExampleComparison] = []
    for c in picked:
        if len(results) >= 6:
            break
        product = (await db.execute(select(Product).where(Product.id == c.product_id))).scalar_one_or_none()
        if not product:
            continue
        line = (product.name.split() or [""])[0]
        if line in seen_lines:
            continue
        cheap, pricey = await extreme(c.product_id, True), await extreme(c.product_id, False)
        if not cheap or not pricey:
            continue
        seen_lines.add(line)
        results.append(ExampleComparison(
            barcode=product.barcode,
            name=product.name,
            brand=product.brand,
            unit_of_measure=product.unit_of_measure,
            cheapest_price=cheap[0],
            cheapest_chain=cheap[1],
            priciest_price=pricey[0],
            priciest_chain=pricey[1],
            stores_count=c.n,
        ))

    _examples_cache = (now, results)
    return results[:limit]


# ─── Endpoint: Product image (via Shufersal CDN) ─────────────────────────────

# Pictures are looked up in app.images (also used in bulk by the worker).

# A redirect is stable; a miss is re-checked only every IMAGE_RECHECK_DAYS, but the worker may find
# the picture sooner, so a 404 is kept for a shorter time.
_IMAGE_HIT_HEADERS = {"Cache-Control": "public, max-age=86400"}
_IMAGE_MISS_HEADERS = {"Cache-Control": "public, max-age=3600"}
IMAGE_RECHECK_DAYS = 14


@router.get("/products/{barcode}/image", summary="Redirect to product image")
async def get_product_image(barcode: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product).where(Product.barcode == barcode))
    product = result.scalar_one_or_none()

    if product is None:
        # Not a product we hold: no lookup (it would send an arbitrary barcode to Shufersal's site).
        raise HTTPException(status_code=404, detail="No image found", headers=_IMAGE_MISS_HEADERS)

    if product.image_url and is_allowed_image_url(product.image_url):
        return RedirectResponse(product.image_url, status_code=302, headers=_IMAGE_HIT_HEADERS)

    # A recent miss is not looked up again on every view.
    recently_missed = bool(
        product.image_checked_at
        and product.image_checked_at > datetime.utcnow() - timedelta(days=IMAGE_RECHECK_DAYS)
    )
    if not recently_missed:
        product_id, product_name = product.id, product.name
        # Give the connection back before the slow call to Shufersal (up to ~16 s): holding it here let a
        # trickle of requests use up the whole pool.
        await db.rollback()
        try:
            image_url = await _lookup_image_url(barcode, product_name)
        except ImageLookupError:
            # Shufersal could not be asked: say nothing about the picture and do not cache it.
            raise HTTPException(status_code=404, detail="No image found", headers={"Cache-Control": "no-store"})
        values = {"image_url": image_url} if image_url else {"image_checked_at": datetime.utcnow()}
        await db.execute(update(Product).where(Product.id == product_id).values(**values))
        await db.commit()
        if image_url:
            return RedirectResponse(image_url, status_code=302, headers=_IMAGE_HIT_HEADERS)

    raise HTTPException(status_code=404, detail="No image found", headers=_IMAGE_MISS_HEADERS)


# ─── Endpoint 3: Basket Comparison ───────────────────────────────────────────

@router.post(
    "/basket/compare",
    response_model=BasketCompareResponse,
    summary="Compare total basket price across all stores",
)
async def compare_basket(
    items: Annotated[List[BasketItem], Field(max_length=100)],     # a real basket is a few dozen at most
    city: Optional[str] = Query(None, max_length=60, description="Only stores whose city contains this text"),
    chain: Optional[str] = Query(None, max_length=60, description="Only stores of this chain (exact name)"),
    limit: Optional[int] = Query(None, ge=1, le=500, description="Return only the best N stores (default: all)"),
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
    # The same product listed twice counts once with the quantities added (otherwise it would look
    # "missing" at every store).
    quantity_map: dict[str, int] = {}
    for item in items:
        quantity_map[item.barcode] = min(99, quantity_map.get(item.barcode, 0) + item.quantity)
    barcodes = list(quantity_map)

    # Step 2: Find all products in the basket
    products_result = await db.execute(
        select(Product).where(Product.barcode.in_(barcodes), _real_barcode())
    )
    products = {p.barcode: p for p in products_result.scalars().all()}

    # Step 3: Get all current prices for all basket products, as plain columns (loading four full ORM
    # entities per row for ~9,000 rows was most of the time).
    by_id = {p.id: p for p in products.values()}
    prices_query = (
        select(
            Price.price, Price.product_id,
            Store.id.label("store_pk"), Store.store_id, Store.name.label("store_name"), Store.city,
            Store.address, Store.latitude, Store.longitude,
            func.coalesce(Store.last_promo_at >= func.now() - timedelta(days=PROMO_FRESH_DAYS), False).label("promo_known"),
            Chain.id.label("chain_pk"), Chain.name.label("chain_name"), Chain.chain_id.label("chain_code"),
        )
        .join(Store, Price.store_id == Store.id)
        .join(Chain, Store.chain_id == Chain.id)
        .where(
            Price.product_id.in_(list(by_id)),
            Price.is_current,
            Price.price > 0,  # a 0 price means "none", never the cheapest
            _not_wholesale(),  # exclude wholesale stores
        )
    )
    if city and city.strip():
        # Same "contains" match the product page uses
        prices_query = prices_query.where(Store.city.icontains(city.strip(), autoescape=True))
    if chain and chain.strip():
        prices_query = prices_query.where(display_chain_name_sql() == chain.strip())

    all_price_rows = (await db.execute(prices_query)).all()

    # Step 4: Group prices by store: store_pk -> (row, {barcode -> item})
    grouped: dict = {}
    for r in all_price_rows:
        product = by_id[r.product_id]
        qty = quantity_map.get(product.barcode, 1)
        entry = grouped.get(r.store_pk)
        if entry is None:
            entry = grouped[r.store_pk] = (r, {})
        entry[1][product.barcode] = {
            "product_name": product.name,
            "barcode": product.barcode,
            "unit_price": r.price,
            "quantity": qty,
            "line_total": r.price * qty,
            "regular_line_total": r.price * qty,
            "promo": None,
        }

    # Step 4b: Promotions, only for stores whose promotion data is fresh. A promotion on one basket product
    # goes on its line (as in B1); one that covers several basket products is a store-level adjustment.
    fresh_stores = [store_pk for store_pk, (r, _) in grouped.items() if r.promo_known]
    promos_by_store = await _basket_promotions(db, list(by_id), fresh_stores)
    id_of = {p.barcode: p.id for p in by_id.values()}
    barcode_of = {pid: barcode for barcode, pid in id_of.items()}
    adjustments_by_store: dict[int, list[dict]] = {}
    for store_pk, promos in promos_by_store.items():
        items_by_barcode = grouped[store_pk][1]
        lines = {id_of[b]: (info["unit_price"], info["quantity"]) for b, info in items_by_barcode.items()}
        for applied in price_store(lines, promos):
            promo = applied.promo
            if len(applied.units) == 1:
                (pid,) = applied.units
                info = items_by_barcode[barcode_of[pid]]
                info["line_total"] = info["regular_line_total"] - applied.saving
                info["promo"] = {"description": promo.description, "min_qty": promo.min_qty,
                                 "price": promo.price, "sets": applied.sets}
            else:
                adjustments_by_store.setdefault(store_pk, []).append({
                    "description": promo.description, "min_qty": promo.min_qty, "price": promo.price,
                    "sets": applied.sets, "saving": applied.saving,
                    "barcodes": [barcode_of[pid] for pid in applied.units],
                })

    # Step 5: Total per store (of the items it has), then sort: complete baskets first, cheapest first
    ranked = []
    for store_pk, (r, items_by_barcode) in grouped.items():
        adjustments = adjustments_by_store.get(store_pk, [])
        adjusted = sum((a["saving"] for a in adjustments), Decimal("0"))
        total = sum((info["line_total"] for info in items_by_barcode.values()), Decimal("0")) - adjusted
        savings = sum((info["regular_line_total"] - info["line_total"] for info in items_by_barcode.values()), Decimal("0")) + adjusted
        ranked.append((len(barcodes) - len(items_by_barcode), total, savings, adjustments, r, items_by_barcode))
    ranked.sort(key=lambda x: (x[0], x[1]))

    complete_totals = [t for missing, t, _, _, _, _ in ranked if missing == 0]
    if len(complete_totals) >= 2:
        max_savings = complete_totals[-1] - complete_totals[0]
        max_total = complete_totals[-1]
    else:
        max_savings = Decimal("0")
        max_total = max((t for _, t, _, _, _, _ in ranked), default=Decimal("0"))
    cheapest_store = ranked[0][4].store_name if ranked else None

    # Step 6: Build the answer. The constructed models skip validation (the values come from the database)
    # and the JSON is written straight from them: a basket answer is ~1.3 MB, so this mattered.
    shown = ranked[:limit] if limit else ranked
    basket_order = {barcode: n for n, barcode in enumerate(barcodes)}
    store_totals = [
        BasketStoreTotal.model_construct(
            store=StoreResponse.model_construct(
                id=r.store_pk, store_id=r.store_id, name=r.store_name, city=r.city, address=r.address,
                latitude=r.latitude, longitude=r.longitude,
                chain=ChainResponse.model_construct(
                    id=r.chain_pk, name=display_chain_name(r.chain_name, r.store_name), chain_id=r.chain_code,
                ),
            ),
            total_price=total,
            items_found=len(items_by_barcode),
            items_missing=missing,
            savings=savings,
            promotions_known=bool(r.promo_known),
            promo_adjustments=adjustments,
            # In the order the items were listed in the basket (the database returns them in no fixed order).
            item_prices=sorted(items_by_barcode.values(), key=lambda i: basket_order[i["barcode"]]),
        )
        for missing, total, savings, adjustments, r, items_by_barcode in shown
    ]

    response = BasketCompareResponse.model_construct(
        stores=store_totals,
        total_items_requested=len(barcodes),
        cheapest_store=cheapest_store,
        max_savings=max_savings,
        total_stores=len(ranked),
        max_total=max_total,
    )
    return Response(content=response.model_dump_json(), media_type="application/json")
