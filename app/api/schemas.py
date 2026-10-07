# app/api/schemas.py

from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime
from typing import Optional, List


# BaseModel from Pydantic automatically:
# - Validates incoming data
# - Converts Python objects to JSON
# - Documents your API automatically

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
    latitude: Optional[float]
    longitude: Optional[float]
    delivery_url: Optional[str]

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
    barcodes: List[str]


class BasketItem(BaseModel):
    """One item in a shopping basket comparison request."""
    barcode: str
    quantity: int = 1  # How many of this item


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