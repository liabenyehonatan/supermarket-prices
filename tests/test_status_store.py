# Maintenance of the scraper library's status JSON.

import json
from datetime import datetime, timedelta, timezone

from app import settings
from app.scraper import status_store


def stamp(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).astimezone().isoformat(sep=" ")


def write_status(root, events, downloads):
    d = root / "status"
    d.mkdir(exist_ok=True)
    (d / "polizer.json").write_text(json.dumps({
        "_metadata": {"x": 1},
        "events": [{"system_timestamp": stamp(a), "file_name": f"e{i}"} for i, a in enumerate(events)],
        "verified_downloads": [{"system_timestamp": stamp(a), "file_name": f"d{i}"} for i, a in enumerate(downloads)],
        "global_status": [{"status": "started"}],
    }))


def read_status(root):
    return json.loads((root / "status" / "polizer.json").read_text())


def test_prune_drops_old_entries_and_keeps_everything_else(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DUMPS_DIR", tmp_path)
    write_status(tmp_path, events=[0, 1, 10, 40], downloads=[0, 5, 20, 90])
    assert status_store.prune("Polizer", event_days=3, download_days=14) == (2, 2)
    data = read_status(tmp_path)
    assert [e["file_name"] for e in data["events"]] == ["e0", "e1"]
    assert [d["file_name"] for d in data["verified_downloads"]] == ["d0", "d1"]
    assert data["global_status"] == [{"status": "started"}] and data["_metadata"] == {"x": 1}


def test_prune_leaves_unparseable_entries_and_missing_files_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DUMPS_DIR", tmp_path)
    assert status_store.prune("Nothing") == (0, 0)
    (tmp_path / "status").mkdir()
    (tmp_path / "status" / "polizer.json").write_text(json.dumps(
        {"events": [{"system_timestamp": "garbage"}], "verified_downloads": [{"file_name": "x"}]}))
    assert status_store.prune("Polizer") == (0, 0)


def test_forget_download(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DUMPS_DIR", tmp_path)
    write_status(tmp_path, events=[], downloads=[0, 0])
    assert status_store.forget_download("Polizer", "d1") is True
    assert [d["file_name"] for d in read_status(tmp_path)["verified_downloads"]] == ["d0"]
    assert status_store.forget_download("Polizer", "d1") is False
    assert status_store.forget_download("Missing", "d1") is False
