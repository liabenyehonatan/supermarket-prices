# app/parser/mass_parser.py
#
# Drives the full parse pipeline for every chain:
#   dumps/<ChainFolder>/<filename>.xml  →  PostgreSQL
#
# Uses il_supermarket_parsers for chain-specific XML parsing, and
# universal_parser for the DB upsert logic.
#
# Run order matters: STORE files first so store records exist before prices.

import asyncio
import logging
from pathlib import Path

from il_supermarket_parsers.parser_factory import ParserFactory
from il_supermarket_parsers.utils.loading_utils import file_name_to_components
from il_supermarket_parsers.utils import DumpFile
from il_supermarket_scarper.utils.file_types import FileTypesFilters
from il_supermarket_scarper.utils.folders_name import DumpFolderNames

from app.db.database import AsyncSessionLocal
from app.parser.universal_parser import (
    get_or_create_chain,
    get_or_create_store_from_price_file,
    upsert_store_from_row,
    get_or_create_product,
    upsert_price,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DUMPS_ROOT = Path(__file__).parent.parent.parent / "dumps"
BATCH_SIZE = 500


# ── File discovery ────────────────────────────────────────────────────────────

def iter_dump_files(
    file_type: FileTypesFilters,
    chains: list[str] = None,
) -> list[DumpFile]:
    """
    Walk dumps/<ChainFolder>/ and return DumpFile objects whose detected
    file type matches `file_type`.

    `chains` is a list of ScraperFactory enum names (e.g. ["SHUFERSAL"]).
    None = all folders found on disk.
    """
    wanted_folders = None
    if chains:
        wanted_folders = {DumpFolderNames[c].value for c in chains}

    result = []

    for folder in sorted(DUMPS_ROOT.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        if wanted_folders and folder.name not in wanted_folders:
            continue

        for xml_file in sorted(folder.glob("*.xml")):
            try:
                dump_file = file_name_to_components(str(folder), xml_file.name)
            except Exception as e:
                logger.warning(f"Could not parse filename {xml_file.name}: {e}")
                continue

            if dump_file.detected_filetype == file_type:
                result.append(dump_file)

    return result


def _get_parser_name_for_folder(folder_name: str) -> str | None:
    """Map a dump folder name to a ParserFactory enum name."""
    folder_to_parser = {v.value: v.name for v in DumpFolderNames}
    return folder_to_parser.get(folder_name)


# ── Store file parsing ────────────────────────────────────────────────────────

async def parse_store_files(chains: list[str] = None):
    """Parse all Stores XML files and upsert store records."""
    store_files = iter_dump_files(FileTypesFilters.STORE_FILE, chains)
    if not store_files:
        logger.info("  No store files found, skipping")
    logger.info(f"Store files to parse: {len(store_files)}")

    for dump_file in store_files:
        folder_name = Path(dump_file.store_folder).name
        parser_name = _get_parser_name_for_folder(folder_name)
        if not parser_name:
            logger.warning(f"No parser found for folder: {folder_name}")
            continue

        try:
            parser_cls = ParserFactory.get(parser_name)
        except ValueError:
            logger.warning(f"ParserFactory has no parser for: {parser_name}")
            continue

        logger.info(f"Parsing stores: {dump_file.file_name} ({folder_name})")
        parser = parser_cls()

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    chain = await get_or_create_chain(
                        session,
                        chain_id=dump_file.extracted_chain_id,
                        folder_name=folder_name,
                    )
                    count = 0
                    async for row in parser.read(dump_file):
                        await upsert_store_from_row(session, chain, row)
                        count += 1
                    logger.info(f"  Upserted {count} stores")
        except Exception as e:
            logger.error(f"Failed to parse {dump_file.file_name}: {e}")


# ── Price file parsing ────────────────────────────────────────────────────────

async def parse_price_files(chains: list[str] = None):
    """Parse all PriceFull and Price (delta) XML files and upsert product + price records."""
    price_files = (
        iter_dump_files(FileTypesFilters.PRICE_FULL_FILE, chains)
        + iter_dump_files(FileTypesFilters.PRICE_FILE, chains)
    )
    logger.info(f"Price files to parse: {len(price_files)}")

    for dump_file in price_files:
        folder_name = Path(dump_file.store_folder).name
        parser_name = _get_parser_name_for_folder(folder_name)
        if not parser_name:
            logger.warning(f"No parser found for folder: {folder_name}")
            continue

        try:
            parser_cls = ParserFactory.get(parser_name)
        except ValueError:
            logger.warning(f"ParserFactory has no parser for: {parser_name}")
            continue

        logger.info(f"Parsing prices: {dump_file.file_name} ({folder_name})")
        parser = parser_cls()

        processed = errors = 0

        try:
            async with AsyncSessionLocal() as session:
                async with session.begin():
                    chain = await get_or_create_chain(
                        session,
                        chain_id=dump_file.extracted_chain_id,
                        folder_name=folder_name,
                    )
                    store = await get_or_create_store_from_price_file(
                        session,
                        chain,
                        store_id=dump_file.extracted_store_number,
                    )

                    async for i, row in _enumerate_async(parser.read(dump_file)):
                        try:
                            product = await get_or_create_product(session, row)
                            if product:
                                await upsert_price(session, product, store, row)
                                processed += 1
                        except Exception as e:
                            errors += 1
                            logger.debug(f"Row error: {e}")

                        if (i + 1) % BATCH_SIZE == 0:
                            await session.flush()
                            logger.info(f"  Progress: {i+1:,} rows")

        except Exception as e:
            logger.error(f"Failed to parse {dump_file.file_name}: {e}")
            continue

        logger.info(f"  Done: {processed:,} prices, {errors} errors")


async def _enumerate_async(agen):
    i = 0
    async for item in agen:
        yield i, item
        i += 1


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_mass_parser(chains: list[str] = None):
    """
    Parse all downloaded XML files for the given chains (or all chains).
    Stores are parsed first so store records exist before price insertion.
    """
    logger.info("=" * 60)
    logger.info("MASS PARSER START")
    logger.info("Step 1/2: parsing store files")
    await parse_store_files(chains)

    logger.info("Step 2/2: parsing price files")
    await parse_price_files(chains)

    logger.info("MASS PARSER DONE")
    logger.info("=" * 60)


if __name__ == "__main__":
    import sys

    # Usage:
    #   python -m app.parser.mass_parser              # all chains
    #   python -m app.parser.mass_parser SHUFERSAL    # one chain
    #   python -m app.parser.mass_parser SHUFERSAL VICTORY

    chain_args = [a.upper() for a in sys.argv[1:]] or None
    asyncio.run(run_mass_parser(chains=chain_args))
