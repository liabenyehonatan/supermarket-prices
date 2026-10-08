# app/parser/universal_parser.py
#
# Bridge layer between normalized row dicts (from il_supermarket_parsers) and
# our PostgreSQL DB: field-name helpers, chain and store upserts. Products and
# prices are loaded in bulk by app/parser/price_loader.py.
#
# Row dicts come with the original XML field names.  Field names vary across
# chains (e.g. ManufacturerName vs ManufactureName), so every lookup uses a
# helper that tries multiple candidate keys.

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chain, Store

logger = logging.getLogger(__name__)

# ── Hebrew display names keyed by DumpFolderNames folder value ───────────────
CHAIN_DISPLAY_NAMES: dict[str, str] = {
    "Bareket":                  "עוף והודו ברקת",
    "YaynotBitanAndCarrefour":  "יינות ביתן / קרפור",
    "Cofix":                    "קופיקס",
    "CityMarketKiryatGat":      "סיטי מרקט קרית גת",
    "CityMarketShops":          "סיטי מרקט",
    "DorAlon":                  "דור אלון",
    "GoodPharm":                "גוד פארם",
    "HaziHinam":                "חצי חינם",
    "HetCohen":                 "ח. כהן",
    "Keshet":                   "קשת טעמים",
    "KingStore":                "קינג סטור",
    "Maayan2000":               "מעיין 2000",
    "MahsaniAShuk":             "מחסני השוק",
    "NetivHased":               "נתיב החסד",
    "MeshnatYosef1":            "משנת יוסף",
    "MeshnatYosef2":            "משנת יוסף 2",
    "Osherad":                  "אושר עד",
    "Polizer":                  "פוליצר",
    "RamiLevy":                 "רמי לוי",
    "SalachDabach":             "סאלח דבאח",
    "ShefaBarcartAshem":        "שפע ברכת השם",
    "Shufersal":                "שופרסל",
    "ShukAhir":                 "שוק העיר",
    "StopMarket":               "סטופ מרקט",
    "SuperPharm":               "סופר פארם",
    "SuperYuda":                "סופר יודה",
    "SuperSapir":               "סופר ספיר",
    "FreshMarketAndSuperDosh":  "פרשמרקט / סופרדוש",
    "Quik":                     "קוויק",
    "TivTaam":                  "טיב טעם",
    "Victory":                  "ויקטורי",
    "VictoryNewSource":         "ויקטורי",
    "Yellow":                   "יילו",
    "Yohananof":                "יוחננוף",
    "ZolVeBegadol":             "זול ובגדול",
    "Wolt":                     "וולט",
}


# ── Field-name helpers ────────────────────────────────────────────────────────

def _get(row: dict, *keys: str, default=None):
    """Return the first non-empty value found among the given keys."""
    for k in keys:
        v = row.get(k) or row.get(k.lower()) or row.get(k.upper())
        if v and str(v).strip():
            return str(v).strip()
    return default


def _safe_decimal(value: Optional[str]) -> Optional[Decimal]:
    if not value or not str(value).strip():
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _safe_float(value: Optional[str]) -> Optional[float]:
    if not value or not str(value).strip():
        return None
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _safe_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


# ── Chain ─────────────────────────────────────────────────────────────────────

async def get_or_create_chain(
    session: AsyncSession,
    chain_id: str,
    folder_name: str,
) -> Chain:
    result = await session.execute(
        select(Chain).where(Chain.chain_id == chain_id)
    )
    chain = result.scalar_one_or_none()

    if chain is None:
        display_name = CHAIN_DISPLAY_NAMES.get(folder_name, folder_name)
        chain = Chain(
            chain_id=chain_id,
            name=display_name,
            is_active=True,
        )
        session.add(chain)
        await session.flush()
        logger.info(f"Created chain: {display_name} ({chain_id})")

    return chain


# ── Store (from price-file metadata) ─────────────────────────────────────────

async def get_or_create_store_from_price_file(
    session: AsyncSession,
    chain: Chain,
    store_id: str,
) -> Store:
    """
    Minimal store record created from a price file's metadata.
    Name/address filled in later when the stores XML is parsed.
    """
    result = await session.execute(
        select(Store).where(
            Store.chain_id == chain.id,
            Store.store_id == store_id,
        )
    )
    store = result.scalar_one_or_none()

    if store is None:
        store = Store(
            chain_id=chain.id,
            store_id=store_id,
            is_active=True,
        )
        session.add(store)
        await session.flush()

    return store


# ── Store (from stores XML file) ──────────────────────────────────────────────

async def upsert_store_from_row(
    session: AsyncSession,
    chain: Chain,
    row: dict,
) -> Optional[Store]:
    """
    Insert or update a store record using data from a Stores XML row.
    """
    store_id = _get(row, "StoreId", "storeid", "STOREID")
    if not store_id:
        return None

    result = await session.execute(
        select(Store).where(
            Store.chain_id == chain.id,
            Store.store_id == store_id,
        )
    )
    store = result.scalar_one_or_none()

    name = _get(row, "StoreName", "storename", "STORENAME")
    city = _get(row, "City", "city", "CITY")
    address = _get(row, "Address", "address", "ADDRESS")
    lat = _safe_float(_get(row, "Latitude", "latitude"))
    lon = _safe_float(_get(row, "Longitude", "longitude"))

    if store is None:
        store = Store(
            chain_id=chain.id,
            store_id=store_id,
            name=name,
            city=city,
            address=address,
            latitude=lat,
            longitude=lon,
            is_active=True,
        )
        session.add(store)
        await session.flush()
    else:
        if name:
            store.name = name
        if city:
            store.city = city
        if address:
            store.address = address
        if lat is not None:
            store.latitude = lat
        if lon is not None:
            store.longitude = lon

    return store
