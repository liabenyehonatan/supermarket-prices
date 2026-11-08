"""One plain async function per MCP tool. Each takes an ApiClient, asks the site's API for what it needs and answers
with a small dict: only what Claude needs to talk to the shopper, never the API's raw JSON."""

import asyncio
import re
import time
from typing import Any, Literal

from mcp_service import config
from mcp_service.errors import ToolUserError
from mcp_service.filters import get_cities, validate_chain, validate_city
from mcp_service.text import clean_text

_BARCODE = re.compile(r"^\d{1,20}$")
STATS_TTL_SECONDS = 300
_stats: tuple[float, str | None] | None = None


def _reset_cache() -> None:
    global _stats
    _stats = None


def _num(value: Any) -> float | None:
    """The API writes prices as decimal strings; Claude gets numbers."""
    return None if value is None else float(value)


def _brand(value: str | None) -> str | None:
    return clean_text(value) or None


def _check_barcodes(barcodes: list[str], maximum: int) -> list[str]:
    if not barcodes:
        raise ToolUserError("לא התקבלו ברקודים.")
    if len(barcodes) > maximum:
        raise ToolUserError(f"עד {maximum} ברקודים בקריאה אחת.")
    for b in barcodes:
        if not _BARCODE.match(b.strip()):
            raise ToolUserError(f"ברקוד לא תקין: \"{b}\" (ספרות בלבד, עד 20 תווים).")
    return [b.strip() for b in barcodes]


async def prices_as_of(api) -> str | None:
    """When the prices were last refreshed (the API's /stats), so Claude can say how fresh the answer is. Cached
    for 5 minutes; a failure here never fails the tool that asked."""
    global _stats
    now = time.monotonic()
    if _stats is None or now - _stats[0] > STATS_TTL_SECONDS:
        try:
            stamp = (await api.get("/api/v1/stats")).get("last_updated")
        except ToolUserError:
            return None
        _stats = (now, stamp)
    return _stats[1]


async def search_products(
    api, queries: list[str], limit: int = config.MAX_SEARCH_LIMIT,
    sort: Literal["relevance", "cheapest", "unit_price"] = "relevance",
) -> dict:
    cleaned = [q.strip() for q in queries]
    if not cleaned or any(not q for q in cleaned):
        raise ToolUserError("צריך לפחות חיפוש אחד, ואף חיפוש לא יכול להיות ריק.")
    if len(cleaned) > config.MAX_QUERIES:
        raise ToolUserError(f"עד {config.MAX_QUERIES} חיפושים בקריאה אחת.")
    if any(len(q) > config.MAX_QUERY_LEN for q in cleaned):
        raise ToolUserError(f"טקסט חיפוש ארוך מדי (עד {config.MAX_QUERY_LEN} תווים).")
    limit = max(1, min(limit, config.MAX_SEARCH_LIMIT))

    async def one(q: str):
        try:
            return await api.get("/api/v1/products/search", {"q": q, "limit": limit}), None
        except ToolUserError as e:
            return [], str(e)

    found = await asyncio.gather(*(one(q) for q in cleaned))
    barcodes = list(dict.fromkeys(p["barcode"] for rows, _ in found for p in rows))
    prices: dict = {}
    warnings: list[str] = []
    if barcodes:
        try:
            prices = await api.post("/api/v1/products/price-summary-batch", {"barcodes": barcodes})
        except ToolUserError:
            warnings.append("המחירים לא זמינים כרגע; התוצאות הן שמות מוצרים בלבד.")

    results = []
    for q, (rows, error) in zip(cleaned, found):
        products = []
        for p in rows:
            s = prices.get(p["barcode"]) or {}
            products.append({
                "barcode": p["barcode"], "name": clean_text(p["name"]), "brand": _brand(p.get("brand")),
                "price_from": _num(s.get("price")), "unit_price": _num(s.get("unit_price")),
                "unit": s.get("unit"), "is_weighted": bool(p.get("is_weighted")),
            })
        if sort != "relevance":
            key = "price_from" if sort == "cheapest" else "unit_price"
            products.sort(key=lambda x: (x[key] is None, x[key] if x[key] is not None else 0))
        results.append({"query": q, "products": products, "error": error})
    out: dict = {"results": results}
    if warnings:
        out["warnings"] = warnings
    return out


async def get_products(api, barcodes: list[str]) -> dict:
    wanted = list(dict.fromkeys(_check_barcodes(barcodes, 100)))
    rows = await api.post("/api/v1/products/by-barcodes", {"barcodes": wanted})
    products = [{"barcode": p["barcode"], "name": clean_text(p["name"]), "brand": _brand(p.get("brand")),
                 "unit": p.get("unit_of_measure")} for p in rows]
    got = {p["barcode"] for p in products}
    return {"products": products, "not_found": [b for b in wanted if b not in got]}


async def get_product_prices(api, barcode: str, city: str | None = None, chain: str | None = None) -> dict:
    (barcode,) = _check_barcodes([barcode], 1)
    if chain:
        chain = await validate_chain(api, chain)
    if city:
        city = await validate_city(api, city)
    data = await api.get(f"/api/v1/products/{barcode}/compare")
    offers = []
    for p in data["prices"]:
        if chain and p["chain_name"] != chain:
            continue
        if city and city.lower() not in (p.get("store_city") or "").lower():
            continue
        promos = p.get("promotions") or []
        delivery = p.get("delivery_url") or ""
        offers.append({
            "chain": p["chain_name"], "city": clean_text(p.get("store_city")) or None, "price": _num(p["price"]),
            "unit_price": _num(p.get("unit_price")),
            "promo": clean_text(promos[0]["description"]) if promos else None,
            "delivery_url": delivery if delivery.startswith("http") else None,
        })
        if len(offers) == 5:
            break
    prod = data["product"]
    out = {
        "product": {"barcode": prod["barcode"], "name": clean_text(prod["name"]), "brand": _brand(prod.get("brand")),
                    "unit": prod.get("unit_of_measure")},
        "offers": offers, "prices_as_of": await prices_as_of(api),
    }
    if not offers:
        out["note"] = "אין הצעות שמתאימות לסינון שביקשת."
    return out


async def find_cities(api, query: str, limit: int = config.MAX_CITIES) -> dict:
    wanted = query.strip().lower()
    if not wanted:
        raise ToolUserError("צריך טקסט לחיפוש עיר.")
    limit = max(1, min(limit, config.MAX_CITIES))
    cities = [c for c in await get_cities(api) if wanted in c.lower()][:limit]
    out: dict = {"cities": cities}
    if not cities:
        out["note"] = "לא נמצאה עיר שמתאימה לטקסט."
    return out


async def list_chains(api) -> dict:
    return {"chains": [{"name": c["name"], "stores": c["stores"]} for c in await api.get("/api/v1/chains")]}


async def list_deals(api, city: str | None = None, chain: str | None = None, q: str | None = None,
                     limit: int = config.MAX_DEALS) -> dict:
    params: dict = {"limit": max(1, min(limit, config.MAX_DEALS))}
    if chain:
        params["chain"] = await validate_chain(api, chain)
    if city:
        params["city"] = await validate_city(api, city)
    if q and q.strip():
        params["q"] = q.strip()[: config.MAX_QUERY_LEN]
    data = await api.get("/api/v1/deals", params)
    return {"deals": [{
        "brand": clean_text(d["brand"]), "description": clean_text(d["description"]), "price": _num(d["price"]),
        "min_qty": d["min_qty"], "saving_pct": round(float(d["saving_pct"]) * 100), "ends_at": d.get("ends_at"),
        "stores": d["stores"],
    } for d in data["deals"]]}
