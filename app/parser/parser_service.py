# app/parser/parser_service.py

import gzip
import logging
from pathlib import Path
from xml.etree.ElementTree import iterparse
from io import BytesIO
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models import Chain, Store, Product, Price

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DUMPS_FOLDER = Path(__file__).parent.parent.parent / "dumps"

# Shufersal's chain ID from the XML — we saw this in the file:
# <ChainID>7290027600007</ChainID>
SHUFERSAL_CHAIN_ID = "7290027600007"
SHUFERSAL_CHAIN_NAME = "שופרסל"


# ─── Helper Functions ────────────────────────────────────────────────────────

def decode_gz_file(filepath: Path) -> str:
    """
    Open a GZ file and return its contents as a string.
    Tries UTF-8 first, falls back to Windows-1255 for older files.
    """
    with gzip.open(filepath, "rb") as f:
        raw = f.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning(f"UTF-8 failed for {filepath.name}, trying windows-1255")
        return raw.decode("windows-1255")


def safe_decimal(value: Optional[str]) -> Optional[Decimal]:
    """
    Safely convert a string to Decimal.
    Returns None if the value is empty or invalid.

    Why Decimal and not float?
    Remember: Decimal is exact. 6.50 stays 6.50.
    Float might become 6.4999999 due to binary rounding.
    """
    if not value or not value.strip():
        return None
    try:
        return Decimal(value.strip())
    except InvalidOperation:
        return None


def safe_datetime(value: Optional[str]) -> Optional[datetime]:
    """
    Safely convert a string to datetime.
    Handles the format we saw in the XML: "2025-12-14T09:46:00"
    Returns None if the value is empty or unparseable.
    """
    if not value or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_xml_items(xml_content: str) -> tuple[dict, list[dict]]:
    """
    Stream-parse the XML content and extract metadata and items.
    Handles both Shufersal format (<root><Items><Item>) 
    and Victory format (<Prices><Products><Product>).
    """
    from io import StringIO

    metadata = {}
    items = []
    current_item = {}
    inside_item = False

    # These are ALL the possible item tag names across chains
    # Shufersal uses "item", Victory uses "product"
    ITEM_TAGS = {"item", "product"}

    # These are all possible metadata tag names
    METADATA_TAGS = {"chainid", "subchainid", "storeid"}

    context = iterparse(StringIO(xml_content), events=("start", "end"))

    for event, elem in context:
        # Normalize tag to lowercase for consistent handling
        tag = elem.tag.lower()

        # When we hit an opening item/product tag
        if event == "start" and tag in ITEM_TAGS:
            inside_item = True
            current_item = {}

        # When we hit a closing item/product tag
        elif event == "end" and tag in ITEM_TAGS:
            inside_item = False
            if current_item:
                items.append(current_item.copy())
            current_item = {}
            elem.clear()

        # Collect metadata from root level
        elif event == "end" and tag in METADATA_TAGS:
            if not inside_item:
                metadata[tag] = elem.text.strip() if elem.text else ""

        # Collect all fields inside an item
        elif event == "end" and inside_item:
            key = tag  # already lowercase
            if elem.text:
                current_item[key] = elem.text.strip()
            else:
                current_item[key] = ""

    return metadata, items

# ─── Database Functions ───────────────────────────────────────────────────────

async def get_or_create_chain(session: AsyncSession) -> Chain:
    """
    Find Shufersal in the chains table, or create it if it doesn't exist.

    "get_or_create" is a very common pattern in database apps:
    - Try to find the record
    - If found, return it
    - If not found, create it and return the new one
    """
    # Try to find existing chain
    result = await session.execute(
        select(Chain).where(Chain.chain_id == SHUFERSAL_CHAIN_ID)
    )
    chain = result.scalar_one_or_none()

    if chain is None:
        logger.info(f"Creating new chain: {SHUFERSAL_CHAIN_NAME}")
        chain = Chain(
            chain_id=SHUFERSAL_CHAIN_ID,
            name=SHUFERSAL_CHAIN_NAME,
            website_url="https://www.shufersal.co.il",
            online_store_url_template="https://www.shufersal.co.il/online/he/search#q={barcode}&t=all",
            is_active=True,
        )
        session.add(chain)
        # flush() sends the INSERT to the DB but doesn't commit yet.
        # We need the chain.id before we can create stores.
        await session.flush()
        logger.info(f"✅ Chain created with ID: {chain.id}")

    return chain


async def get_or_create_store(
    session: AsyncSession,
    chain: Chain,
    store_id: str,
    store_name: str,
) -> Store:
    """
    Find a store by chain + store_id, or create it if it doesn't exist.
    """
    result = await session.execute(
        select(Store).where(
            Store.chain_id == chain.id,
            Store.store_id == store_id,
        )
    )
    store = result.scalar_one_or_none()

    if store is None:
        logger.info(f"Creating new store: {store_name} (ID: {store_id})")
        store = Store(
            chain_id=chain.id,
            store_id=store_id,
            name=store_name,
            is_active=True,
        )
        session.add(store)
        await session.flush()

    return store


async def get_or_create_product(
    session: AsyncSession,
    item: dict,
) -> Optional[Product]:
    """
    Find a product by barcode, or create it if it doesn't exist.

    If the product already exists (same barcode seen in another store),
    we don't update its name — first one wins. This avoids overwriting
    clean Hebrew names with slightly different versions from other chains.
    """
    barcode = item.get("itemcode", "").strip()
    if not barcode:
        return None

    result = await session.execute(
        select(Product).where(Product.barcode == barcode)
    )
    product = result.scalar_one_or_none()

    if product is None:
        product = Product(
            barcode=barcode,
            name=item.get("itemname", ""),
            # Handle multiple manufacturer field names across chains
            brand=(
                item.get("manufacturername")
                or item.get("manufacturename")
                or None
            ),
            manufacturer=(
                item.get("manufacturername")
                or item.get("manufacturename")
                or None
            ),
            # Handle both UnitOfMeasure (Shufersal) and UnitMeasure (Victory)
            unit_of_measure=(
                item.get("unitofmeasure")
                or item.get("unitmeasure")
                or None
            ),
            # Handle both bIsWeighted and BisWeighted
            is_weighted=(
                item.get("bisweighted", "0") == "1"
                or item.get("bisweighted", "0") == "1"
            ),
        )
        session.add(product)
        await session.flush()

    return product


async def upsert_price(
    session: AsyncSession,
    product: Product,
    store: Store,
    item: dict,
) -> None:
    """
    Insert or update the price for a product in a store.

    "Upsert" = Update if exists, Insert if not.

    Our strategy for price history:
    - Find the current active price for this product+store
    - If the price CHANGED: mark old one as not current, insert new one
    - If the price is the SAME: just update the scraped_at timestamp
    """
    price_value = safe_decimal(item.get("itemprice"))
    if price_value is None:
        return

    unit_price_value = safe_decimal(item.get("unitofmeasureprice"))
    # Handle both PriceUpdateTime and PriceUpdateDate
    price_updated_at = (
        safe_datetime(item.get("priceupdatetime"))
        or safe_datetime(item.get("priceupdatedate"))
        or datetime.now()
    )
    # Find existing current price for this product+store
    result = await session.execute(
        select(Price).where(
            Price.product_id == product.id,
            Price.store_id == store.id,
            Price.is_current == True,
        )
    )
    existing_price = result.scalar_one_or_none()

    if existing_price is None:
        # No price exists yet — create a new one
        new_price = Price(
            product_id=product.id,
            store_id=store.id,
            price=price_value,
            unit_price=unit_price_value,
            price_updated_at=price_updated_at,
            is_current=True,
        )
        session.add(new_price)

    elif existing_price.price != price_value:
        # Price changed! Mark old price as historical
        existing_price.is_current = False

        # Insert new current price
        new_price = Price(
            product_id=product.id,
            store_id=store.id,
            price=price_value,
            unit_price=unit_price_value,
            price_updated_at=price_updated_at,
            is_current=True,
        )
        session.add(new_price)

    else:
        # Price unchanged — just update the scraped_at timestamp
        existing_price.scraped_at = datetime.now()


# ─── Main Parser Function ─────────────────────────────────────────────────────

async def parse_file(filepath: Path, store_name: str) -> dict:
    """
    Parse a single GZ file and insert all its data into the database.

    Returns a summary dict with counts of what was processed.
    """
    logger.info(f"\n📄 Parsing file: {filepath.name}")

    # Step 1: Read and decode the GZ file
    xml_content = decode_gz_file(filepath)
    logger.info(f"File decoded successfully ({len(xml_content):,} characters)")

    # Step 2: Parse the XML into Python dicts
    metadata, items = parse_xml_items(xml_content)
    logger.info(f"Found {len(items):,} items in XML")
    logger.info(f"Metadata: ChainID={metadata.get('chainid')}, StoreID={metadata.get('storeid')}")

    if not items:
        logger.warning("No items found in file, skipping")
        return {"items": 0, "errors": 0}

    # Step 3: Insert into database
    processed = 0
    errors = 0

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Get or create the chain
            chain = await get_or_create_chain(session)

            # Get or create the store
            # Use lowercase key — we normalized in parse_xml_items
            store_id = metadata.get("storeid", "unknown")
            store = await get_or_create_store(
                session=session,
                chain=chain,
                store_id=store_id,
                store_name=store_name,
            )

            # Process each item
            # We commit in batches of 500 for performance.
            # Committing every single item = 50,000 commits = very slow.
            # Committing everything at once = one huge transaction = risky.
            # Batches of 500 = balanced approach.
            BATCH_SIZE = 500

            for i, item in enumerate(items):
                try:
                    product = await get_or_create_product(session, item)
                    if product:
                        await upsert_price(session, product, store, item)
                        processed += 1

                    # Commit every 500 items
                    if (i + 1) % BATCH_SIZE == 0:
                        await session.flush()
                        logger.info(f"  Progress: {i+1:,}/{len(items):,} items processed")

                except Exception as e:
                    errors += 1
                    logger.warning(f"Error processing item {item.get('ItemCode', '?')}: {e}")
                    continue

    logger.info(f"✅ Done: {processed:,} items inserted/updated, {errors} errors")
    return {"items": processed, "errors": errors}


async def run_parser():
    """
    Parse all GZ files in the Shufersal dumps folder.
    """
    shufersal_folder = DUMPS_FOLDER / "Shufersal"

    if not shufersal_folder.exists():
        logger.error(f"Dumps folder not found: {shufersal_folder}")
        return

    # Find all GZ files
    gz_files = list(shufersal_folder.glob("*.gz"))

    if not gz_files:
        logger.error("No GZ files found! Run the scraper first.")
        return

    logger.info(f"🚀 Starting parser...")
    logger.info(f"Found {len(gz_files)} GZ files to parse")

    total_items = 0
    total_errors = 0

    for filepath in gz_files:
        # Extract store name from filename
        # e.g. "199 - דיל בת ים- בלפור.gz" → "199 - דיל בת ים- בלפור"
        store_name = filepath.stem

        result = await parse_file(filepath, store_name)
        total_items += result["items"]
        total_errors += result["errors"]

    logger.info("\n" + "="*50)
    logger.info("📊 PARSING SUMMARY")
    logger.info(f"  Files parsed: {len(gz_files)}")
    logger.info(f"  ✅ Total items processed: {total_items:,}")
    logger.info(f"  ❌ Total errors: {total_errors}")
    logger.info("="*50)

async def run_victory_parser():
    """
    Parse all GZ files in the Victory dumps folder.
    Similar to run_parser() but with Victory chain info.
    """
    victory_folder = DUMPS_FOLDER / "Victory"

    if not victory_folder.exists():
        logger.error("Victory dumps folder not found! Run victory scraper first.")
        return

    gz_files = list(victory_folder.glob("*.gz"))

    if not gz_files:
        logger.error("No Victory GZ files found!")
        return

    logger.info(f"🚀 Starting Victory parser...")
    logger.info(f"Found {len(gz_files)} GZ files")

    total_items = 0
    total_errors = 0

    # Victory chain constants
    victory_chain_id = "7290696200003"
    victory_chain_name = "ויקטורי"

    for filepath in gz_files:
        logger.info(f"\n📄 Parsing: {filepath.name}")

        xml_content = decode_gz_file(filepath)
        metadata, items = parse_xml_items(xml_content)

        logger.info(f"Found {len(items):,} items")

        if not items:
            continue

        processed = 0
        errors = 0

        async with AsyncSessionLocal() as session:
            async with session.begin():

                # Get or create Victory chain
                result = await session.execute(
                    select(Chain).where(Chain.chain_id == victory_chain_id)
                )
                chain = result.scalar_one_or_none()

                if chain is None:
                    chain = Chain(
                        chain_id=victory_chain_id,
                        name=victory_chain_name,
                        website_url="https://www.victory.co.il",
                        is_active=True,
                    )
                    session.add(chain)
                    await session.flush()
                    logger.info(f"✅ Created Victory chain")

                # Get store ID from metadata
                store_id = metadata.get("storeid", "unknown")
                store_name = f"Victory {store_id}"

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
                        name=store_name,
                        is_active=True,
                    )
                    session.add(store)
                    await session.flush()

                BATCH_SIZE = 500
                for i, item in enumerate(items):
                    try:
                        product = await get_or_create_product(session, item)
                        if product:
                            await upsert_price(session, product, store, item)
                            processed += 1

                        if (i + 1) % BATCH_SIZE == 0:
                            await session.flush()
                            logger.info(f"  Progress: {i+1:,}/{len(items):,}")

                    except Exception as e:
                        errors += 1
                        logger.warning(f"Error: {e}")
                        continue

        total_items += processed
        total_errors += errors
        logger.info(f"✅ Done: {processed:,} items, {errors} errors")

    logger.info("\n" + "="*50)
    logger.info("📊 VICTORY PARSING SUMMARY")
    logger.info(f"  ✅ Total items: {total_items:,}")
    logger.info(f"  ❌ Total errors: {total_errors}")
    logger.info("="*50)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import sys

    # Run with: python -m app.parser.parser_service
    # Or:       python -m app.parser.parser_service victory
    if len(sys.argv) > 1 and sys.argv[1] == "victory":
        asyncio.run(run_victory_parser())
    else:
        asyncio.run(run_parser())