# app/parser/mass_parser.py
#
# Drives the parse pipeline for the chains downloaded into dumps/:
#   dumps/<ChainFolder>/<filename>.xml  →  PostgreSQL
#
# Uses il_supermarket_parsers for chain-specific XML parsing, universal_parser
# for chain/store upserts and price_loader for the bulk product/price load.
#
# Guarantees
#  - Each file is one transaction: data + ledger row commit together or not at all.
#  - A file already marked done in ingested_files is never parsed again.
#  - Files are applied oldest first, stores before prices, so a late file can
#    never overwrite a newer price.
#  - One chain failing (or one poison file) never stops the other chains/files.
#  - The XML is deleted (when DELETE_AFTER_INGEST is on) only after commit.

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lxml import etree
from il_supermarket_parsers.parser_factory import ParserFactory
from il_supermarket_parsers.utils import DumpFile
from il_supermarket_parsers.utils.loading_utils import file_name_to_components
from il_supermarket_scarper.utils.file_types import FileTypesFilters
from il_supermarket_scarper.utils.folders_name import DumpFolderNames

from app import settings
from app.db.database import AsyncSessionLocal
from app.parser import ledger
from app.parser.price_loader import load_price_rows
from app.pipeline.shutdown import STOP
from app.scraper import status_store
from app.parser.universal_parser import (
    get_or_create_chain,
    get_or_create_store_from_price_file,
    upsert_store_from_row,
)

logger = logging.getLogger(__name__)

DUMPS_ROOT = settings.DUMPS_DIR

_FILE_TYPE_LABEL = {
    FileTypesFilters.STORE_FILE: "store",
    FileTypesFilters.PRICE_FULL_FILE: "price_full",
    FileTypesFilters.PRICE_FILE: "price",
}


# ── Result objects ────────────────────────────────────────────────────────────

@dataclass
class ChainParseResult:
    folder: str
    files_ok: int = 0
    files_failed: int = 0
    files_quarantined: int = 0
    files_skipped: int = 0      # already loaded, nothing to do
    rows_applied: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.files_failed == 0 and self.files_quarantined == 0:
            return "ok"
        return "partial" if self.files_ok > 0 else "failed"


class CorruptFile(Exception):
    """The file itself is unusable (cut off, not XML, or yields nothing)."""


# ── File integrity ────────────────────────────────────────────────────────────

# A price file smaller than this may legitimately hold no items.
_EMPTY_OK_BYTES = 2048


def assert_well_formed(path: Path) -> None:
    """
    Raise unless the whole file is well-formed XML.

    The chain parsers stream items and do NOT notice a truncated download: a
    file cut off halfway happily yields the items before the cut. Loading it
    would look like a successful run and, for a full file, make us close every
    product after the cut. A full streaming pass (fast, C-speed, constant
    memory) catches that before anything is written.
    """
    try:
        for _, element in etree.iterparse(str(path), events=("end",), huge_tree=True):
            element.clear()
    except etree.XMLSyntaxError as exc:
        raise CorruptFile(f"not well-formed XML: {exc}") from exc


# ── File discovery ────────────────────────────────────────────────────────────

def folder_for_chain(chain_name: str) -> str:
    """ScraperFactory enum name (SHUFERSAL) → dump folder name (Shufersal)."""
    return DumpFolderNames[chain_name].value


def _chain_name_for_folder(folder_name: str) -> Optional[str]:
    return {v.value: v.name for v in DumpFolderNames}.get(folder_name)


def _dump_files_in(folder: Path) -> list[DumpFile]:
    result = []
    for xml_file in sorted(folder.glob("*.xml")):
        try:
            result.append(file_name_to_components(str(folder), xml_file.name))
        except Exception as exc:
            logger.warning("Could not parse filename %s: %s", xml_file.name, exc)
    return result


def iter_dump_files(
    file_type: FileTypesFilters,
    chains: Optional[list[str]] = None,
) -> list[DumpFile]:
    """
    Walk dumps/<ChainFolder>/ and return DumpFile objects of one detected type.
    `chains` is a list of ScraperFactory enum names (e.g. ["SHUFERSAL"]);
    None = every chain folder on disk.
    """
    wanted = {folder_for_chain(c) for c in chains} if chains else None
    result = []
    for folder in sorted(DUMPS_ROOT.iterdir()) if DUMPS_ROOT.exists() else []:
        if not folder.is_dir() or folder.name.startswith((".", "_")):
            continue
        if wanted is not None and folder.name not in wanted:
            continue
        result.extend(f for f in _dump_files_in(folder) if f.detected_filetype == file_type)
    return result


def _sort_key(dump_file: DumpFile):
    # Oldest first. On the same minute a Full file goes before a delta.
    full_first = 0 if dump_file.detected_filetype == FileTypesFilters.PRICE_FULL_FILE else 1
    return (dump_file.extracted_date, full_first, dump_file.file_name)


# ── One file ──────────────────────────────────────────────────────────────────

async def _parse_store_file(dump_file: DumpFile, parser_cls, folder_name: str) -> tuple[int, int]:
    """Load one Stores file. Returns (rows_total, rows_applied)."""
    await asyncio.to_thread(assert_well_formed, Path(dump_file.get_full_path))
    parser = parser_cls()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            chain = await get_or_create_chain(
                session, chain_id=dump_file.extracted_chain_id, folder_name=folder_name
            )
            count = 0
            async for row in parser.read(dump_file):
                if await upsert_store_from_row(session, chain, row) is not None:
                    count += 1
            await ledger.record_done(
                session, folder_name, dump_file.file_name, "store",
                rows_total=count, rows_applied=count, rows_skipped=0,
            )
    return count, count


async def _parse_price_file(dump_file: DumpFile, parser_cls, folder_name: str) -> tuple[int, int, str]:
    """Load one PriceFull / Price file. Returns (rows_total, rows_applied, summary)."""
    if not dump_file.extracted_store_number:
        raise ValueError("file name carries no store number")

    path = Path(dump_file.get_full_path)
    await asyncio.to_thread(assert_well_formed, path)
    is_full = dump_file.detected_filetype == FileTypesFilters.PRICE_FULL_FILE
    parser = parser_cls()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            chain = await get_or_create_chain(
                session, chain_id=dump_file.extracted_chain_id, folder_name=folder_name
            )
            store = await get_or_create_store_from_price_file(
                session, chain, store_id=dump_file.extracted_store_number
            )
            stats = await load_price_rows(
                session, store, parser.read(dump_file),
                is_full=is_full, fallback_ts=dump_file.extracted_date,
            )
            if stats.rows_total == 0 and path.stat().st_size > _EMPTY_OK_BYTES:
                # A real file that yields nothing means the parser no longer
                # understands it. Fail loudly instead of recording an empty success.
                raise CorruptFile(f"parsed 0 rows from {path.stat().st_size} bytes")
            await ledger.record_done(
                session, folder_name, dump_file.file_name,
                "price_full" if is_full else "price",
                rows_total=stats.rows_total,
                rows_applied=stats.rows_applied,
                rows_skipped=stats.invalid + stats.stale_ignored,
            )
    summary = (
        f"{stats.rows_total:,} rows: +{stats.inserted} new, {stats.changed} changed, "
        f"{stats.unchanged} same, {stats.stale_ignored} stale, {stats.invalid} invalid, "
        f"{stats.closed_missing} closed"
    )
    return stats.rows_total, stats.rows_applied, summary


async def _record_failure(folder_name: str, dump_file: DumpFile, error: str) -> str:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            return await ledger.record_failure(
                session, folder_name, dump_file.file_name,
                _FILE_TYPE_LABEL.get(dump_file.detected_filetype, "unknown"), error,
            )


# ── One chain ─────────────────────────────────────────────────────────────────

async def parse_chain(chain_name: str) -> ChainParseResult:
    """
    Parse every not-yet-loaded store and price file of one chain.
    Never raises for data problems; they are counted in the result.
    """
    folder_name = folder_for_chain(chain_name)
    result = ChainParseResult(folder=folder_name)
    folder = DUMPS_ROOT / folder_name
    if not folder.is_dir():
        return result

    parser_name = _chain_name_for_folder(folder_name)
    try:
        parser_cls = ParserFactory.get(parser_name)
    except Exception as exc:
        result.errors.append(f"no parser for {folder_name}: {exc}")
        result.files_failed += 1
        logger.error("No parser for %s: %s", folder_name, exc)
        return result

    async with AsyncSessionLocal() as session:
        ledger_rows = await ledger.load_ledger(session, folder_name)

    wanted_types = (
        FileTypesFilters.STORE_FILE,
        FileTypesFilters.PRICE_FULL_FILE,
        FileTypesFilters.PRICE_FILE,
    )
    pending: list[DumpFile] = []
    for dump_file in _dump_files_in(folder):
        if dump_file.detected_filetype not in wanted_types:
            continue
        entry = ledger_rows.get(dump_file.file_name)
        path = folder / dump_file.file_name
        if entry and entry.status == ledger.DONE:
            # Loaded earlier; a crash between commit and delete leaves the file.
            result.files_skipped += 1
            ledger.delete_loaded_file(path)
        elif entry and entry.status == ledger.QUARANTINED:
            ledger.quarantine_file(path)
            result.files_skipped += 1
        else:
            pending.append(dump_file)

    # Stores first (so price files find their store), then oldest-first.
    pending.sort(key=lambda f: (f.detected_filetype != FileTypesFilters.STORE_FILE, _sort_key(f)))
    if pending:
        logger.info("%s: %d files to load (%d already done)", folder_name, len(pending), result.files_skipped)

    for dump_file in pending:
        if STOP.is_set():
            logger.info("%s: stop requested, leaving %d files for the next run", folder_name, len(pending))
            break
        path = folder / dump_file.file_name
        is_store = dump_file.detected_filetype == FileTypesFilters.STORE_FILE
        try:
            if is_store:
                _, applied = await _parse_store_file(dump_file, parser_cls, folder_name)
                summary = f"{applied} stores"
            else:
                _, applied, summary = await _parse_price_file(dump_file, parser_cls, folder_name)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.error("%s: failed %s: %s", folder_name, dump_file.file_name, error)
            try:
                status = await _record_failure(folder_name, dump_file, error)
            except Exception as ledger_exc:  # DB itself is down: stop this chain, retry next cycle
                result.errors.append(f"ledger write failed: {ledger_exc}")
                result.files_failed += 1
                break
            if status == ledger.QUARANTINED:
                ledger.quarantine_file(path)
                result.files_quarantined += 1
            else:
                result.files_failed += 1
                if isinstance(exc, CorruptFile):
                    # A damaged download will not heal by re-reading it. Drop it and
                    # make the scraper fetch a fresh copy next cycle; the ledger
                    # counts the attempts, so a file that is broken at the source
                    # ends up quarantined instead of looping.
                    path.unlink(missing_ok=True)
                    status_store.forget_download(folder_name, dump_file.file_name)
            result.errors.append(f"{dump_file.file_name}: {error}")
            continue

        result.files_ok += 1
        result.rows_applied += applied
        logger.info("%s: %s — %s", folder_name, dump_file.file_name, summary)
        ledger.delete_loaded_file(path)

    return result


# ── All chains ────────────────────────────────────────────────────────────────

def chains_on_disk() -> list[str]:
    """ScraperFactory names of every chain folder present in dumps/."""
    if not DUMPS_ROOT.exists():
        return []
    names = []
    for folder in sorted(DUMPS_ROOT.iterdir()):
        if folder.is_dir() and not folder.name.startswith((".", "_")):
            name = _chain_name_for_folder(folder.name)
            if name:
                names.append(name)
    return names


async def run_mass_parser(chains: Optional[list[str]] = None) -> dict[str, ChainParseResult]:
    """Parse the given chains (default: everything in dumps/), one after another."""
    logger.info("=" * 60)
    logger.info("MASS PARSER START")
    results: dict[str, ChainParseResult] = {}
    for chain_name in chains or chains_on_disk():
        try:
            results[chain_name] = await parse_chain(chain_name)
        except Exception as exc:  # defensive: parse_chain handles its own errors
            logger.exception("Chain %s crashed", chain_name)
            failed = ChainParseResult(folder=chain_name, files_failed=1)
            failed.errors.append(f"{type(exc).__name__}: {exc}")
            results[chain_name] = failed
    logger.info("MASS PARSER DONE")
    logger.info("=" * 60)
    return results


async def _main(chain_args: Optional[list[str]]) -> int:
    from app.pipeline.lock import AlreadyRunning, ingest_lock

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    try:
        async with ingest_lock():
            results = await run_mass_parser(chains=chain_args)
    except AlreadyRunning:
        logger.error("Another ingest run holds the lock; not starting.")
        return 2
    return 0 if all(r.status == "ok" for r in results.values()) else 1


if __name__ == "__main__":
    import sys

    # Usage:
    #   python -m app.parser.mass_parser              # all chains in dumps/
    #   python -m app.parser.mass_parser SHUFERSAL    # one chain
    #   python -m app.parser.mass_parser SHUFERSAL VICTORY_NEW_SOURCE
    sys.exit(asyncio.run(_main([a.upper() for a in sys.argv[1:]] or None)))
