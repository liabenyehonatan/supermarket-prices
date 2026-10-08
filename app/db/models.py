# app/db/models.py

# ── Imports ────────────────────────────────────────────────────────────────
# We import the specific "column types" we need from SQLAlchemy.
# Each type maps to a real PostgreSQL data type under the hood.
from sqlalchemy import (
    String,      # → PostgreSQL VARCHAR  (text with a max length)
    Text,        # → PostgreSQL TEXT     (unlimited length text)
    Integer,     # → PostgreSQL INTEGER  (whole numbers: 1, 2, 42)
    Numeric,     # → PostgreSQL NUMERIC  (exact decimal numbers — critical for money)
    Float,       # → PostgreSQL FLOAT    (approximate decimal — ok for coordinates)
    Boolean,     # → PostgreSQL BOOLEAN  (True / False)
    DateTime,    # → PostgreSQL TIMESTAMP (date + time)
    ForeignKey,  # → Creates a link between two tables
    Index,       # → Creates a database index for faster searching
    func,        # → Lets us use SQL functions like NOW()
    text,        # → Raw SQL fragments (used for partial-index conditions)
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
# Mapped and mapped_column are the modern way (SQLAlchemy 2.0+) to define columns.
# relationship() defines how two tables are connected in Python.

from datetime import datetime
from decimal import Decimal
from typing import Optional
from app.db.base import Base  # The foundation class we just created


# ════════════════════════════════════════════════════════════════════════════
# TABLE 1: chains
# One row per supermarket company (Shufersal, Rami Levy, Victory, etc.)
# ════════════════════════════════════════════════════════════════════════════
class Chain(Base):
    __tablename__ = "chains"
    # __tablename__ tells SQLAlchemy what to call this table in PostgreSQL.
    # Convention: table names are lowercase and plural.

    # PRIMARY KEY — every table needs one. It's a unique ID for each row.
    # Integer is fine here — we won't have more than a few hundred chains.
    # autoincrement=True means the database assigns 1, 2, 3... automatically.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The chain's official ID from the XML files (e.g. "7290027600007" for Shufersal).
    # String(20) → VARCHAR(20) in PostgreSQL. Max 20 characters is plenty for these IDs.
    # unique=True → no two chains can have the same chain_id (enforced by the DB).
    # nullable=False → this column MUST have a value, it can never be empty.
    chain_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    # The human-readable name. String(100) is generous for any chain name.
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # The base URL of the chain's website. Text = unlimited length.
    # nullable=True (the default) → allowed to be empty. Not all chains have websites.
    website_url: Mapped[Optional[str]] = mapped_column(Text)

    # For "transfer basket" feature — the URL pattern we'd use to link to their
    # online store. e.g. "https://www.shufersal.co.il/online/he/search?q={barcode}"
    # nullable=True because not all chains support online shopping yet.
    online_store_url_template: Mapped[Optional[str]] = mapped_column(Text)

    # Whether this chain is currently being scraped and shown in the app.
    # Boolean → True/False. server_default="true" means PostgreSQL sets it to
    # True automatically when we insert a new chain without specifying this field.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # RELATIONSHIP — this is Python-only, it doesn't create a column.
    # It tells SQLAlchemy: "a Chain has many Stores".
    # back_populates="chain" means the Store class has a matching relationship.
    stores: Mapped[list["Store"]] = relationship("Store", back_populates="chain")

    def __repr__(self):
        # __repr__ is just a helper so when you print a Chain object in Python
        # you see something useful instead of <Chain object at 0x7f...>
        return f"<Chain {self.name}>"


# ════════════════════════════════════════════════════════════════════════════
# TABLE 2: stores
# One row per physical branch. A chain has many stores.
# ════════════════════════════════════════════════════════════════════════════
class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FOREIGN KEY — this is the link to the chains table.
    # "chains.id" means: this column must contain a value that exists in chains.id.
    # This enforces that you can't create a store without a valid chain.
    chain_id: Mapped[int] = mapped_column(ForeignKey("chains.id"), nullable=False)

    # The store's ID from the XML (e.g. "001", "042").
    # Combined with chain_id this uniquely identifies any branch in Israel.
    store_id: Mapped[str] = mapped_column(String(20), nullable=False)

    # Human-readable name like "שופרסל דיל תל אביב רוטשילד"
    name: Mapped[Optional[str]] = mapped_column(String(200))

    city: Mapped[Optional[str]] = mapped_column(String(100))
    address: Mapped[Optional[str]] = mapped_column(String(200))

    # ── Location columns (your requirement) ─────────────────────────────────
    # WHY Float and not Numeric?
    # Numeric is for EXACT decimals (money — where 6.50 must never become 6.4999999).
    # Float is for APPROXIMATE decimals where tiny rounding errors don't matter.
    # GPS coordinates like 32.0853 don't need cent-level precision — a few meters
    # of rounding is perfectly fine. Float also uses less storage than Numeric.
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)

    # For the "transfer basket" feature — the specific URL for THIS store's
    # online delivery page (if the chain supports per-store URLs).
    delivery_url: Mapped[Optional[str]] = mapped_column(Text)

    # Is this store currently active / open? Lets us hide closed branches.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # RELATIONSHIPS
    chain: Mapped["Chain"] = relationship("Chain", back_populates="stores")
    prices: Mapped[list["Price"]] = relationship("Price", back_populates="store")
    promotions: Mapped[list["Promotion"]] = relationship(
        "Promotion", back_populates="store"
    )

    # CONSTRAINT — the combination of chain_id + store_id must be unique.
    # Because store "001" exists in Shufersal AND in Rami Levy — the store_id
    # alone isn't enough to identify a branch. Together they are unique.
    __table_args__ = (
        Index("ix_stores_chain_store", "chain_id", "store_id", unique=True),
        Index("ix_stores_location", "latitude", "longitude"),
        # ix_stores_location speeds up queries like "find all stores near me"
    )

    def __repr__(self):
        return f"<Store {self.name} ({self.city})>"


# ════════════════════════════════════════════════════════════════════════════
# TABLE 3: products
# One row per unique product across ALL chains.
# The barcode (GTIN) is the universal product identifier.
# ════════════════════════════════════════════════════════════════════════════
class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The barcode — this is the GLOBAL identifier for a product.
    # A bottle of Tanova milk has the same barcode in Shufersal and Rami Levy.
    # String(20) covers all GTIN formats (GTIN-8, GTIN-12, GTIN-13, GTIN-14).
    # unique=True — one row per product, no duplicates.
    barcode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)

    # Product name in Hebrew. Text = unlimited length (some names are long).
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # ── Visual & brand columns (your requirement) ────────────────────────────
    # The brand name (e.g. "תנובה", "עלית", "שטראוס").
    # Separate from name so you can filter/group by brand later.
    brand: Mapped[Optional[str]] = mapped_column(String(200))

    # URL to the product image.
    # WHY Text and not String(500)?
    # URLs can be very long especially with CDN parameters. Text has no limit.
    image_url: Mapped[Optional[str]] = mapped_column(Text)

    # The manufacturer's name (often same as brand but sometimes different).
    manufacturer: Mapped[Optional[str]] = mapped_column(String(200))

    # What category the product belongs to (dairy, meat, snacks...).
    # Useful for filtering and basket analysis later.
    category: Mapped[Optional[str]] = mapped_column(String(100))

    # Unit of measure from the XML (e.g. "יחידה", "ק״ג", "ליטר")
    unit_of_measure: Mapped[Optional[str]] = mapped_column(String(50))

    # Is this product sold by weight? (e.g. deli meat, cheese)
    # Affects how price comparison works in the basket.
    is_weighted: Mapped[bool] = mapped_column(Boolean, server_default="false")

    # When we first saw this product in any XML file.
    # server_default=func.now() → PostgreSQL sets this to the current
    # timestamp automatically when the row is inserted. You never set it manually.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # RELATIONSHIPS
    prices: Mapped[list["Price"]] = relationship("Price", back_populates="product")
    promotions: Mapped[list["Promotion"]] = relationship(
        "Promotion", back_populates="product"
    )

    # Barcode lookups use the index behind `unique=True` on the column above, so
    # no separate barcode index is declared (it would duplicate that one).
    __table_args__ = (
    # gin_trgm_ops tells PostgreSQL to use the trigram operator
    # from pg_trgm for this index. Without this, PostgreSQL
    # doesn't know HOW to build a GIN index on plain text.
    Index(
        "ix_products_name_trgm",
        "name",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    ),
)

    def __repr__(self):
        return f"<Product {self.barcode}: {self.name}>"


# ════════════════════════════════════════════════════════════════════════════
# TABLE 4: prices
# The heart of the app. One row per product+store, updated on every scrape.
# Also keeps history so you can see price changes over time.
# ════════════════════════════════════════════════════════════════════════════
class Price(Base):
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # FOREIGN KEYS — link to both products and stores tables.
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)

    # ── WHY Numeric and NOT Float for price? ────────────────────────────────
    # This is one of the most important decisions in any financial application.
    #
    # Float example of the problem:
    #   >>> 6.50 + 3.30
    #   9.799999999999999   ← WRONG! Should be 9.80
    #
    # This happens because computers store floats in binary, and most decimal
    # fractions can't be represented exactly in binary.
    #
    # Numeric(10, 2) means:
    #   10 → total digits allowed (e.g. 99999999.99)
    #   2  → exactly 2 decimal places (cents)
    # PostgreSQL stores this as an EXACT value, like a calculator — not binary float.
    # For a basket total of 50 products, those tiny float errors add up to
    # visible wrong totals. Always use Numeric/Decimal for money.
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # The price per unit of measure (e.g. price per 100g for weighted items).
    # Nullable because not all products have a unit price.
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # When was this price last seen in the XML file?
    # This is what you show users: "Price as of May 4, 2025"
    price_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # When did OUR scraper insert/update this row?
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # Is this the current price or a historical record?
    # When we scrape a new price, we set the old row's is_current to False
    # and insert a new row with is_current=True.
    # This gives you price history for free!
    is_current: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # RELATIONSHIPS
    product: Mapped["Product"] = relationship("Product", back_populates="prices")
    store: Mapped["Store"] = relationship("Store", back_populates="prices")

    __table_args__ = (
        # THE integrity rule of the price history: a (store, product) pair has at
        # most one current row. Also serves the loader's per-store lookups.
        Index(
            "uq_prices_current_store_product",
            "store_id",
            "product_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        # Serves every API read ("current prices of product X in all stores") and
        # carries store_id + price so the cheapest-price queries can skip the heap.
        Index(
            "ix_prices_current_product",
            "product_id",
            postgresql_include=["store_id", "price"],
            postgresql_where=text("is_current"),
        ),
        # Fillfactor/autovacuum are applied by the migration (ALTER TABLE ... SET).
    )

    def __repr__(self):
        return f"<Price {self.price} NIS (product={self.product_id}, store={self.store_id})>"


# ════════════════════════════════════════════════════════════════════════════
# TABLE 5: promotions
# Active deals: buy 2 get 1, percentage off, member-only prices, etc.
# ════════════════════════════════════════════════════════════════════════════
class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)

    # The chain's own ID for this promotion (from the XML).
    promotion_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Human-readable description in Hebrew.
    # e.g. "קנה 2 שלם 1" / "הנחה של 15%" / "מחיר מועדון"
    description: Mapped[Optional[str]] = mapped_column(Text)

    # The discounted price after the promotion is applied.
    discounted_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # Minimum quantity needed to trigger the promotion.
    # e.g. min_qty=2 for "buy 2 get 1 free"
    min_qty: Mapped[Optional[int]] = mapped_column(Integer)

    # When does the promotion start and end?
    # Nullable because some promotions in the XML don't have end dates.
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Is this promotion still active right now?
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")

    # RELATIONSHIPS
    product: Mapped["Product"] = relationship("Product", back_populates="promotions")
    store: Mapped["Store"] = relationship("Store", back_populates="promotions")

    __table_args__ = (
        Index("ix_promotions_product_store", "product_id", "store_id"),
        Index("ix_promotions_active", "is_active"),
        # Prevents inserting the same promotion twice for the same store.
        Index(
            "ix_promotions_unique",
            "promotion_id",
            "store_id",
            unique=True,
        ),
    )

    def __repr__(self):
        return f"<Promotion {self.promotion_id}: {self.description}>"


# ════════════════════════════════════════════════════════════════════════════
# TABLE 6: ingested_files
# Ledger of every XML file the parser has handled. This (not "does the file
# exist on disk") is how we know a file was loaded, so files can be deleted
# after loading without ever being parsed twice.
# ════════════════════════════════════════════════════════════════════════════
class IngestedFile(Base):
    __tablename__ = "ingested_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # dumps/<source_folder>/<file_name>  (e.g. "Shufersal", "PriceFull729...xml")
    source_folder: Mapped[str] = mapped_column(String(100), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # "store" | "price_full" | "price"
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # "done" | "failed" | "quarantined"
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_applied: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[Optional[str]] = mapped_column(Text)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("source_folder", "file_name", name="uq_ingested_files_source_name"),
    )

    def __repr__(self):
        return f"<IngestedFile {self.source_folder}/{self.file_name} {self.status}>"


# ════════════════════════════════════════════════════════════════════════════
# TABLE 7: ingest_runs
# One row per worker cycle (chain = NULL) and one per chain and phase inside it.
# This is the source of truth for "is the pipeline healthy".
# ════════════════════════════════════════════════════════════════════════════
class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("ingest_runs.id", ondelete="CASCADE")
    )

    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # NULL for a whole cycle, otherwise the scraper name (e.g. "SHUFERSAL").
    chain: Mapped[Optional[str]] = mapped_column(String(100))
    # "cycle" | "scrape" | "parse"
    phase: Mapped[str] = mapped_column(String(10), nullable=False)
    # "running" | "ok" | "partial" | "failed"
    status: Mapped[str] = mapped_column(String(10), nullable=False)

    files_ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    files_failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_applied: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_ingest_runs_started", "started_at"),
        Index("ix_ingest_runs_phase_status", "phase", "status", "finished_at"),
    )

    def __repr__(self):
        return f"<IngestRun {self.phase} {self.chain or 'ALL'} {self.status}>"
