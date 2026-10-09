# app/scraper/status_store.py
#
# Maintenance of the scraper library's own memory, dumps/status/<chain>.json.
#
# Two collections matter:
#   verified_downloads  file names it considers downloaded (never fetched again)
#   events              a log line for every file it saw on every run
#
# The library re-reads the whole JSON for every file it checks and appends
# thousands of events per run, so left alone the file grows without bound and
# every cycle gets slower. prune() trims both. forget_download() lets the parser
# make the scraper fetch a corrupt file a second time.
#
# Only call these while no scraper process for that chain is running.

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app import settings

logger = logging.getLogger(__name__)


def status_path(folder_name: str) -> Path:
    return settings.DUMPS_DIR / "status" / f"{folder_name.lower()}.json"


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _older_than(entry: dict, cutoff: datetime) -> bool:
    try:
        stamp = datetime.fromisoformat(str(entry.get("system_timestamp")))
    except ValueError:
        return False                      # unreadable: keep rather than guess
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp < cutoff


def prune(folder_name: str, event_days: int = 3, download_days: int = 60) -> tuple[int, int]:
    """
    Drop events older than `event_days` and verified downloads older than
    `download_days`. Some portals list over a month of full files per store, so
    this must stay longer than that, or the same old files are fetched again and
    again. A file forgotten and fetched anyway is never loaded twice: the ingest
    ledger and the newest-full-per-store rule both skip it.
    Returns (events_removed, downloads_removed).
    """
    path = status_path(folder_name)
    data = _read(path)
    if data is None:
        return 0, 0

    now = datetime.now(timezone.utc)
    events = data.get("events", [])
    downloads = data.get("verified_downloads", [])
    keep_events = [e for e in events if not _older_than(e, now - timedelta(days=event_days))]
    keep_downloads = [d for d in downloads if not _older_than(d, now - timedelta(days=download_days))]
    removed = (len(events) - len(keep_events), len(downloads) - len(keep_downloads))
    if removed != (0, 0):
        data["events"] = keep_events
        data["verified_downloads"] = keep_downloads
        _write(path, data)
        logger.info("%s status pruned: -%d events, -%d download records", folder_name, *removed)
    return removed


def forget_download(folder_name: str, file_name: str) -> bool:
    """Make the scraper treat `file_name` as never downloaded. True if it was known."""
    path = status_path(folder_name)
    data = _read(path)
    if data is None:
        return False
    downloads = data.get("verified_downloads", [])
    kept = [d for d in downloads if d.get("file_name") != file_name]
    if len(kept) == len(downloads):
        return False
    data["verified_downloads"] = kept
    _write(path, data)
    return True
