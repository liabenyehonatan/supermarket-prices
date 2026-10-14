# app/api/schemas.py

from pydantic import BaseModel, Field, StringConstraints, field_validator
from decimal import Decimal
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional, List
from zoneinfo import ZoneInfo

_ISRAEL = ZoneInfo("Asia/Jerusalem")


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """The database stores UTC without a zone (now()); say so, so a browser does not read it as local time."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _israel_to_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Chains publish PriceUpdateDate in Israel local time, without a zone."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=_ISRAEL).astimezone(timezone.utc)


# BaseModel from Pydantic automatically:
# - Validates incoming data
# - Converts Python objects to JSON
# - Documents your API automatically

class StatsResponse(BaseModel):
    chains: int
    stores: int
    products: int
    last_updated: Optional[datetime] = None

    @field_validator("last_updated")
    @classmethod
    def _last_updated_is_utc(cls, v):
        return _utc(v)


class ExampleComparison(BaseModel):
    """A well-stocked product with a real price gap, shown on the home page."""
    barcode: str
    name: str
    brand: Optional[str]
    unit_of_measure: Optional[str]
    cheapest_price: Decimal
    cheapest_chain: str
    priciest_price: Decimal
    priciest_chain: str
    stores_count: int


class UnitPriceInfo(BaseModel):
    """Cheapest current price per unit of measure (e.g. per 100 g) for one product."""
    unit_price: Decimal
    unit: Optional[str] = None


class ChainResponse(BaseModel):
    id: int
    name: str
    chain_id: str

    class Config:
        from_attributes = True


class StoreResponse(BaseModel):
    id: int
    store_id: str
    name: Optional[str]
    city: Optional[str]
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    chain: ChainResponse

    class Config:
        from_attributes = True


class ProductSearchResult(BaseModel):
    """Returned when searching for products by name or barcode."""
    id: int
    barcode: str
    name: str
    brand: Optional[str]
    image_url: Optional[str]
    unit_of_measure: Optional[str]
    is_weighted: bool

    class Config:
        from_attributes = True


class PromoInfo(BaseModel):
    """A promotion a store runs on a product: the chain's own wording, not a computed price."""
    description: str
    min_qty: Optional[int] = None
    ends_at: Optional[datetime] = None

    @field_validator("ends_at")
    @classmethod
    def _ends_is_utc(cls, v):
        return _israel_to_utc(v)


class PriceAtStore(BaseModel):
    """A single price entry at a specific store."""
    store_id: int
    store_name: Optional[str]
    store_city: Optional[str]
    store_address: Optional[str]
    chain_name: str
    price: Decimal
    unit_price: Optional[Decimal]
    price_updated_at: datetime
    scraped_at: Optional[datetime] = None  # last time a chain file confirmed this price
    latitude: Optional[float]
    longitude: Optional[float]
    delivery_url: Optional[str]
    promotions: List[PromoInfo] = []

    @field_validator("scraped_at")
    @classmethod
    def _scraped_is_utc(cls, v):
        return _utc(v)

    @field_validator("price_updated_at")
    @classmethod
    def _updated_is_utc(cls, v):
        return _israel_to_utc(v)

    class Config:
        from_attributes = True


class ProductCompareResponse(BaseModel):
    """
    Returned when comparing prices of one product across all stores.
    This is the core response for the price comparison feature.
    """
    product: ProductSearchResult
    # Prices sorted cheapest first
    prices: List[PriceAtStore]
    cheapest_price: Decimal
    most_expensive_price: Decimal
    price_difference: Decimal  # How much you save by choosing cheapest


class CheapestPriceRequest(BaseModel):
    """A list of barcodes to look up the cheapest current price for, in one call."""
    # At most 100 barcodes of at most 20 characters per call (a real page asks for ~20).
    barcodes: Annotated[List[Annotated[str, StringConstraints(max_length=20)]], Field(max_length=100)]


class BasketItem(BaseModel):
    """One item in a shopping basket comparison request."""
    barcode: str = Field(min_length=1, max_length=20)
    quantity: int = Field(1, ge=1, le=99)  # How many of this item (a negative total would rank first)


class BasketStoreTotal(BaseModel):
    """
    The total cost of the entire basket at one specific store.
    This is the core of the basket comparison feature.
    """
    store: StoreResponse
    total_price: Decimal
    # How many of the requested items this store actually has
    items_found: int
    items_missing: int
    # Breakdown per item
    item_prices: List[dict]
    # What the promotions took off this store's shelf total (0 when none applied), and whether we hold
    # fresh promotion data for it (a store without it is priced at shelf price, which may be too high).
    savings: Decimal = Decimal("0")
    promotions_known: bool = False
    # Promotions that cover several products at once: each is subtracted from the total as a whole
    # ({description, min_qty, price, sets, saving, barcodes}); single-product promotions are on their lines.
    promo_adjustments: List[dict] = []


class BasketCompareResponse(BaseModel):
    """
    Returned when comparing a full shopping basket across all stores.
    Stores are sorted cheapest total first.
    """
    # Sorted cheapest to most expensive
    stores: List[BasketStoreTotal]
    total_items_requested: int
    cheapest_store: Optional[str]
    max_savings: Decimal  # Difference between cheapest and most expensive
    # How many stores matched in total (the list may be cut to the best `limit`), and the highest total
    # among complete baskets (what "you save" is measured against).
    total_stores: int = 0
    max_total: Decimal = Decimal("0")

class ChainListItem(BaseModel):
    """A chain as users know it (brands told apart), with how many stores we hold for it."""
    name: str
    stores: int


class DealProduct(BaseModel):
    barcode: str
    name: str
    brand: Optional[str] = None
    image_url: Optional[str] = None
    unit_of_measure: Optional[str] = None


class Deal(BaseModel):
    """A promotion at a brand, measured against the cheapest shelf price we know of its products."""
    deal_id: str
    brand: str
    description: str
    kind: Literal["single", "group"]
    min_qty: int
    price: Decimal                 # for min_qty units
    unit_price: Decimal
    ref_price: Decimal             # cheapest shelf price anywhere (of the cheapest product, for a group)
    saving_pct: Decimal            # a fraction: 0.25 is 25%
    vs_market: bool = False        # the reference includes another brand's price (else: the brand's own shelf only)
    stores: int
    products: int
    max_qty: Optional[int] = None
    ends_at: Optional[datetime] = None
    sample_products: List[DealProduct] = []

    @field_validator("ends_at")
    @classmethod
    def _ends_is_utc(cls, v):
        return _israel_to_utc(v)


class DealFacet(BaseModel):
    name: str
    count: int


class DealRules(BaseModel):
    """The rules a promotion must pass to be listed: the page explains them to shoppers, so they come from here."""
    min_saving: Decimal            # a fraction: 0.10 is 10%
    max_saving: Decimal            # above this a "saving" is almost always a data error
    min_reference_price: Decimal   # a lower cheapest price is a placeholder, never a basis for comparison


class DealsResponse(BaseModel):
    total: int
    deals: List[Deal]
    chains: List[DealFacet]
    rules: DealRules
