# Settings must survive the way docker compose delivers .env values.

import importlib
import re
from pathlib import Path

import pytest

from app import settings

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def reloaded(monkeypatch):
    """Reload app.settings under a patched environment; restore it afterwards."""

    def load(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(settings)

    yield load
    monkeypatch.undo()
    importlib.reload(settings)


def test_inline_comments_in_env_values_are_ignored(reloaded):
    # compose passes everything after "=" through, comment included.
    s = reloaded(
        RETRY_MAX="2   # a failed cycle is retried this many times",
        HISTORY_RETENTION_DAYS="       # empty = keep every price row",
        SKIP_BLOCKED_CHAINS="false     # keep false on an Israeli server",
        RUN_AT="06:00,18:00            # daily cycles",
        HEALTHCHECK_URL="https://hc-ping.com/abc  # worker check",
        RETRY_AFTER_HOURS="1.5 # hours",
    )
    assert s.RETRY_MAX == 2
    assert s.HISTORY_RETENTION_DAYS is None
    assert s.SKIP_BLOCKED_CHAINS is False
    assert s.RUN_AT == "06:00,18:00"
    assert s.HEALTHCHECK_URL == "https://hc-ping.com/abc"
    assert s.RETRY_AFTER_HOURS == 1.5


def test_a_hash_inside_a_value_is_kept(reloaded):
    s = reloaded(HEALTHCHECK_URL="https://example.com/path#fragment")
    assert s.HEALTHCHECK_URL == "https://example.com/path#fragment"


def test_blank_values_fall_back_to_defaults(reloaded):
    s = reloaded(RUN_AT="", RETRY_MAX="", SCRAPE_PROMOS="")
    assert s.RUN_AT == "06:00,18:00" and s.RETRY_MAX == 2 and s.SCRAPE_PROMOS is False


def test_env_example_has_no_inline_comments():
    """Every value in .env.example must be safe for docker compose."""
    bad = [
        line for line in (ROOT / ".env.example").read_text().splitlines()
        if re.match(r"^[A-Z_0-9]+=.*\s#", line)
    ]
    assert bad == []


def test_promos_are_off_unless_scraping_them_is_on(reloaded):
    s = reloaded(SCRAPE_PROMOS="false", PROMO_CHAINS="")
    assert s.promos_enabled_for("SHUFERSAL") is False


def test_promos_on_for_every_chain_when_the_list_is_empty(reloaded):
    s = reloaded(SCRAPE_PROMOS="true", PROMO_CHAINS="")
    assert s.promos_enabled_for("SHUFERSAL") is True and s.promos_enabled_for("RAMI_LEVY") is True


def test_promos_limited_to_the_listed_chains(reloaded):
    s = reloaded(SCRAPE_PROMOS="true", PROMO_CHAINS="shufersal, RAMI_LEVY   # first two")
    assert s.PROMO_CHAINS == {"SHUFERSAL", "RAMI_LEVY"}
    assert s.promos_enabled_for("RAMI_LEVY") is True
    assert s.promos_enabled_for("VICTORY_NEW_SOURCE") is False
