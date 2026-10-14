# Promotions, Phase A (display only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the chains' promotion files into the database and show, on the product page, which stores run a promotion on that product, quoting the chain's own promotion text. No price is computed from a promotion.

**Architecture:** The worker already downloads promo files when `SCRAPE_PROMOS` is on. `parse_chain` gets a third file kind (`PromoFull`) loaded after the price files, one transaction per file together with its ledger row. Per store, the promotions table is a snapshot: each newer full file replaces that store's rows. A pure normaliser (`normalize_promotion`) filters out everything we cannot show honestly (club/coupon/cancelled/expired/gift/huge promos). `/products/{barcode}/compare` attaches up to 3 active promotions per store; the frontend shows them in the store row.

**Tech Stack:** Python 3.11, SQLAlchemy 2 async, Alembic, FastAPI, `il_supermarket_parsers`, pytest (real PostgreSQL `sm_pytest`), React 18 + TypeScript + Vite.

**Spec:** the research conclusions of this session (no separate spec file): ~90% of promotions are reward codes 1/3/10 ("N for X"), reward 6 puts the gift's price in `DiscountedPrice` (never show it as an item price), ~2% are club-only, 27 promotions carry >1,000 items (club-wide or spend-threshold), the three XML layouts differ. Code meanings come from the Fourth Schedule of the Israeli price-transparency regulations (1 = quantity condition, 2 = percent, 3 = amount off an item, 5 = club, 7 = second/third free, 10 = product bundle).

## Global Constraints

- Money is `Decimal`/`Numeric(10, 2)`, never `float`. All DB access is async (`AsyncSession`).
- XML field names are lowercase in parsed rows (`row.get("promotionid")`).
- Store ids are chain-scoped: always look stores up by `(chain_id, store_id)`.
- One transaction per file: promotion rows + `ingested_files` ledger row commit together; the XML is deleted only after commit (`ledger.delete_loaded_file`).
- Run `assert_well_formed` before the parser reads a file.
- Chunks of `settings.PARSE_BATCH_SIZE` (500); never one query per row.
- Schema change = Alembic migration. The API role `api_ro` is read-only; `promotions` is readable already (default privileges), so no new GRANT.
- "Never delete price rows" applies to `prices`. `promotions` is a current-state snapshot, replaced per store by each newer full file.
- Do not touch the `dumps/status` dedup or the ledger semantics.
- UI copy is Hebrew, RTL. Muted look; reuse existing CSS tokens (`--orange-50`, `--orange-700`). Mint is reserved for "cheapest".
- Work on a new branch: `git switch -c promotions-phase-a main`. Commit per task; push and PR only when the user says so. Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A promotion whose only item is parsed as a dict instead of a list (the library does this for one-element lists): must still load.
2. The same `(promotion_id, product)` appearing twice in one file (Victory repeats promotions): must not violate the unique index and must not abort the file.
3. A valid file with zero promotions must clear that store's old promotions; a truncated file must leave them untouched (the integrity check fails before the delete).
4. An expired or not-yet-started promotion stored in the table must never be returned by the API; a product with no promotions returns `promotions: []` (not null, not missing).
5. Barcodes we do not know (not in `products`) must be skipped silently, never create products and never fail the file.

## File Structure

| File | Responsibility |
|---|---|
| `app/settings.py` (modify) | `PROMO_CHAINS` + `promos_enabled_for(chain)` |
| `app/scraper/mass_scraper.py` (modify) | download promo files only for enabled chains |
| `migrations/versions/j7f4d0a69c31_promotions_unique_per_product.py` (create) | unique index includes `product_id` |
| `app/db/models.py` (modify) | same index in the model |
| `app/parser/promo_loader.py` (create) | `PromoRecord`, `normalize_promotion` (pure), `replace_store_promotions` (DB) |
| `app/parser/ledger.py` (modify) | `record_superseded(..., file_type=...)` |
| `app/parser/mass_parser.py` (modify) | promo file kind: discovery, ordering, supersede, load |
| `app/api/schemas.py`, `app/api/routes.py` (modify) | `PromoInfo`, `promotions` on `PriceAtStore`, active-promotion query |
| `frontend/src/types.ts`, `components/StoreRow.tsx`, `pages/ProductPage.tsx`, `styles/global.css` (modify) | show promotions |
| `tests/xml_samples.py`, `tests/test_settings.py`, `tests/test_promo_loader.py` (create), `tests/test_parse_chain.py`, `tests/test_api.py` (modify) | tests |
| `.env.example`, `docker-compose.yml`, `docs/deployment.md`, `CLAUDE.md` (modify) | config and docs |

Run tests with: `venv/bin/python -m pytest <path> -v` (this repo's `venv`; the `venv/bin/pytest` shebang is broken).

---

### Task 1: `PROMO_CHAINS` setting and chain-aware promo download

**Files:**
- Modify: `app/settings.py:80-82`
- Modify: `app/scraper/mass_scraper.py:88-119`
- Modify: `.env.example:67-68`, `docker-compose.yml:125`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `settings.PROMO_CHAINS: set[str]`; `settings.promos_enabled_for(chain: str) -> bool` (chain = ScraperFactory name such as `"SHUFERSAL"`); `mass_scraper._file_types(chain: Optional[str] = None) -> list[str]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_settings.py`)

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_settings.py -v -k promos`
Expected: FAIL with `AttributeError: module 'app.settings' has no attribute 'promos_enabled_for'`.

- [ ] **Step 3: Implement** — in `app/settings.py` replace the `SCRAPE_PROMOS` block:

```python
# Download and load promotion files. Off by default: they take disk and database space.
SCRAPE_PROMOS = _bool("SCRAPE_PROMOS", False)
# Limit promotions to these chains (scraper names, comma separated). Empty = every chain.
PROMO_CHAINS = {c.upper() for c in _list("PROMO_CHAINS")}


def promos_enabled_for(chain: str) -> bool:
    """Whether promotion files are downloaded and loaded for this chain (a ScraperFactory name)."""
    return SCRAPE_PROMOS and (not PROMO_CHAINS or chain.upper() in PROMO_CHAINS)
```

(Keep the existing `SKIP_BLOCKED_CHAINS` line below it.) In `app/scraper/mass_scraper.py`:

```python
def _file_types(chain: Optional[str] = None) -> list[str]:
    """Store lists and full price files, plus full promotion files for the chains that have them on.
    Delta (Price) files are deliberately not used: a daily full file is self-correcting,
    a delta stream can miss changes."""
    types = [FileTypesFilters.STORE_FILE.name, FileTypesFilters.PRICE_FULL_FILE.name]
    if chain is not None and settings.promos_enabled_for(chain):
        types.append(FileTypesFilters.PROMO_FULL_FILE.name)
    return types
```

and in `scrape_chain` change the call to `_run_runner([chain], 1, limit, _file_types(chain))`. In `.env.example` replace the promo comment/line with:

```
# Download and load promotion files (shown on the product page). Needs disk and database space:
# turn on for one or two chains first, e.g. PROMO_CHAINS=SHUFERSAL,RAMI_LEVY, and watch the size.
SCRAPE_PROMOS=false
PROMO_CHAINS=
```

and in `docker-compose.yml` add under `SCRAPE_PROMOS:` the line `      PROMO_CHAINS: ${PROMO_CHAINS:-}`.

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_settings.py -v`
Expected: all PASS. Then `grep -rn "_file_types(" app tests` must show only the call in `scrape_chain` and no other caller broken.

- [ ] **Step 5: Commit**

```bash
git switch -c promotions-phase-a main
git add app/settings.py app/scraper/mass_scraper.py tests/test_settings.py .env.example docker-compose.yml
git commit -m "Promotions: PROMO_CHAINS limits which chains download promo files"
```

---

### Task 2: Unique index per (promotion, store, product)

The existing unique index `ix_promotions_unique (promotion_id, store_id)` allows only one product per promotion per store, but one promotion lists many products.

**Files:**
- Create: `migrations/versions/j7f4d0a69c31_promotions_unique_per_product.py`
- Modify: `app/db/models.py` (the `Promotion.__table_args__` index)
- Test: `tests/test_migration.py`

**Interfaces:**
- Produces: unique index `ix_promotions_unique` on `(promotion_id, store_id, product_id)`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_migration.py`)

```python
async def test_one_promotion_can_cover_many_products_in_a_store(_database):
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("TRUNCATE chains RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO chains (chain_id, name) VALUES ('1', 'c')")
        await conn.execute("INSERT INTO stores (chain_id, store_id) VALUES (1, 's')")
        await conn.execute("INSERT INTO products (barcode, name) VALUES ('a', 'n'), ('b', 'n')")
        await conn.execute(
            "INSERT INTO promotions (product_id, store_id, promotion_id, is_active) VALUES (1, 1, 'p', true), (2, 1, 'p', true)"
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO promotions (product_id, store_id, promotion_id, is_active) VALUES (1, 1, 'p', true)"
            )
    finally:
        await conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_migration.py::test_one_promotion_can_cover_many_products_in_a_store -v`
Expected: FAIL (`UniqueViolationError` on the second INSERT of the setup, because the old index allows one product).

- [ ] **Step 3: Write the migration**

```python
"""promotions: unique per (promotion, store, product)

Revision ID: j7f4d0a69c31
Revises: i6e3c9f58b20
Create Date: 2026-10-14 10:00:00

One promotion lists many products; the old unique index (promotion_id, store_id) allowed one.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "j7f4d0a69c31"
down_revision: Union[str, None] = "i6e3c9f58b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_promotions_unique", table_name="promotions")
    op.create_index("ix_promotions_unique", "promotions", ["promotion_id", "store_id", "product_id"], unique=True)


def downgrade() -> None:
    # The table is derived data (rebuilt from the next full promo file), and the narrower index
    # cannot hold a promotion with several products.
    op.execute("DELETE FROM promotions")
    op.drop_index("ix_promotions_unique", table_name="promotions")
    op.create_index("ix_promotions_unique", "promotions", ["promotion_id", "store_id"], unique=True)
```

In `app/db/models.py` change the unique `Index("ix_promotions_unique", "promotion_id", "store_id", unique=True)` to `Index("ix_promotions_unique", "promotion_id", "store_id", "product_id", unique=True)` and its comment to "one row per product of a promotion in a store".

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_migration.py -v`
Expected: all PASS (including the existing downgrade/upgrade roundtrip). Then `venv/bin/python -m alembic heads` prints only `j7f4d0a69c31 (head)`.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/j7f4d0a69c31_promotions_unique_per_product.py app/db/models.py tests/test_migration.py
git commit -m "Promotions: unique index includes the product (one promotion covers many)"
```

---

### Task 3: `normalize_promotion` (pure filter and shape handling)

**Files:**
- Create: `app/parser/promo_loader.py`
- Test: `tests/test_promo_loader.py` (create)

**Interfaces:**
- Produces:

```python
@dataclass
class PromoRecord:
    promotion_id: str
    description: str
    discounted_price: Optional[Decimal]
    min_qty: Optional[int]
    start_date: Optional[datetime]   # naive Israel local time, as the chains publish
    end_date: Optional[datetime]
    barcodes: list[str]              # unique, in file order

def normalize_promotion(row: dict, *, as_of: datetime) -> Optional[PromoRecord]
```

Returns `None` for anything not shown in Phase A: no id/description, cancelled (`מבוטל`) or coupon text (`קופון...`), not for everyone (any club id other than `0`, or a coupon flag), reward code not in `{1, 2, 3, 10}`, ended before `as_of`, no items, or more than 100 distinct items.

- [ ] **Step 1: Write the failing tests** (`tests/test_promo_loader.py`)

```python
# Pure tests of the promotion filter. Row shapes are the ones il_supermarket_parsers really yields
# (lowercase keys; nested single elements come as dicts, repeated ones as lists).

from datetime import datetime
from decimal import Decimal

import pytest

from app.parser.promo_loader import normalize_promotion

AS_OF = datetime(2026, 5, 12, 6, 0)


def row(**over):
    base = {
        "promotionid": "1", "promotiondescription": "2 ב-18",
        "promotionstartdate": "2026-05-01", "promotionstarthour": "00:00:00",
        "promotionenddate": "2026-12-31", "promotionendhour": "23:59:00",
        "rewardtype": "1", "minqty": "2.00", "discountedprice": "18.00",
        "clubs": {"clubid": "0"},
        "promotionitems": {"item": [{"itemcode": "111"}, {"itemcode": "222"}]},
    }
    base.update(over)
    return base


def test_keeps_a_plain_quantity_promotion():
    rec = normalize_promotion(row(), as_of=AS_OF)
    assert rec.promotion_id == "1" and rec.description == "2 ב-18"
    assert rec.min_qty == 2 and rec.discounted_price == Decimal("18.00")
    assert rec.start_date == datetime(2026, 5, 1, 0, 0) and rec.end_date == datetime(2026, 12, 31, 23, 59)
    assert rec.barcodes == ["111", "222"]


def test_a_single_item_arrives_as_a_dict_not_a_list():
    rec = normalize_promotion(row(promotionitems={"item": {"itemcode": "111"}}), as_of=AS_OF)
    assert rec.barcodes == ["111"]


def test_group_layout_with_item_level_reward_and_millisecond_dates():
    victory = {
        "promotionid": "250678", "promotiondescription": "19.90 יין",
        "promotionstartdatetime": "2026-05-04T00:00:00.000", "promotionenddatetime": "2026-05-30T00:00:00.000",
        "clubid": "0", "additionaliscoupon": "0",
        "groups": {"group": {"groupid": "1", "promotionitems": {"promotionitem": {
            "itemcode": "7290006696595", "rewardtype": "3", "minqty": "1", "discountedprice": "19.9"}}}},
    }
    rec = normalize_promotion(victory, as_of=AS_OF)
    assert rec.barcodes == ["7290006696595"] and rec.min_qty == 1
    assert rec.discounted_price == Decimal("19.90")
    assert rec.end_date == datetime(2026, 5, 30, 0, 0)


def test_date_only_end_means_end_of_that_day():
    rec = normalize_promotion(row(promotionendhour=""), as_of=AS_OF)
    assert rec.end_date == datetime(2026, 12, 31, 23, 59, 59)


def test_duplicate_barcodes_collapse_keeping_order():
    items = {"item": [{"itemcode": "222"}, {"itemcode": "111"}, {"itemcode": "222"}]}
    assert normalize_promotion(row(promotionitems=items), as_of=AS_OF).barcodes == ["222", "111"]


def test_fractional_min_qty_is_kept_without_a_quantity():
    assert normalize_promotion(row(minqty="0.50"), as_of=AS_OF).min_qty is None


@pytest.mark.parametrize("over", [
    {"promotiondescription": "מבוטל"},
    {"promotiondescription": "קופון חטיפים ב 25 שח"},
    {"promotiondescription": ""},
    {"promotionid": ""},
    {"clubs": {"clubid": ["1", "2"]}},
    {"clubs": None, "clubid": "1"},
    {"additionaliscoupon": "1"},
    {"additionalrestrictions": {"additionaliscoupon": "1"}},
    {"rewardtype": "6"},
    {"rewardtype": "7"},
    {"promotionenddate": "2026-05-11"},
    {"promotionitems": {"item": []}},
    {"promotionitems": None},
    {"promotionitems": {"item": [{"itemcode": str(i)} for i in range(101)]}},
])
def test_everything_we_cannot_show_honestly_is_dropped(over):
    assert normalize_promotion(row(**over), as_of=AS_OF) is None


def test_a_hundred_items_is_still_fine():
    items = {"item": [{"itemcode": str(i)} for i in range(100)]}
    assert len(normalize_promotion(row(promotionitems=items), as_of=AS_OF).barcodes) == 100
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v`
Expected: FAIL at import: `ModuleNotFoundError: No module named 'app.parser.promo_loader'`.

- [ ] **Step 3: Write `app/parser/promo_loader.py`** (normaliser part; the DB function comes in Task 4)

```python
# app/parser/promo_loader.py
#
# Load a chain's PromoFull file into `promotions`.
#
# Phase A shows the chain's own promotion text next to a product; no price is computed from a
# promotion. So only what can be shown honestly is kept: promotions for everybody (no club, coupon
# or credit-card audience), of the "N for X" family (reward codes 1, 2, 3, 10), still running, with a
# product list small enough to be a product promotion (club-wide and spend-threshold promotions list
# tens of thousands of items). Reward 6 ("buy X get a gift") is dropped on purpose: its
# DiscountedPrice is the gift's price, not the item's.
#
# The parser library yields one dict per promotion with lowercase keys. Nested elements arrive as a
# dict when there is one and as a list when there are several, and the three chain layouts differ
# (items under promotionitems/item, or under groups/group/promotionitems/promotionitem), so every
# lookup below accepts both shapes.

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from app.parser.price_loader import _clean_text, _money
from app.parser.universal_parser import _safe_datetime, _safe_decimal

logger = logging.getLogger(__name__)

ALLOWED_REWARD_TYPES = {"1", "2", "3", "10"}
MAX_ITEMS_PER_PROMOTION = 100
_CANCELLED = "מבוטל"
_COUPON_PREFIX = "קופון"
_MAX_DESCRIPTION = 300


@dataclass
class PromoRecord:
    promotion_id: str
    description: str
    discounted_price: Optional[Decimal]
    min_qty: Optional[int]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    barcodes: list[str] = field(default_factory=list)


def _as_list(value: Any) -> list:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _text(container: Any, *keys: str) -> Optional[str]:
    """First non-empty scalar among `keys` of a dict, as stripped text."""
    if not isinstance(container, dict):
        return None
    for key in keys:
        value = container.get(key)
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return None


def _items(row: dict) -> list[dict]:
    found: list[dict] = []

    def collect(container: Any) -> None:
        if isinstance(container, dict):
            for key in ("item", "promotionitem"):
                found.extend(i for i in _as_list(container.get(key)) if isinstance(i, dict))

    collect(row.get("promotionitems"))
    groups = row.get("groups")
    for group in _as_list(groups.get("group") if isinstance(groups, dict) else None):
        if isinstance(group, dict):
            collect(group.get("promotionitems"))
    return found


def _club_ids(row: dict) -> set[str]:
    ids: set[str] = set()
    single = _text(row, "clubid")
    if single:
        ids.add(single)
    clubs = row.get("clubs")
    if isinstance(clubs, dict):
        ids.update(str(c).strip() for c in _as_list(clubs.get("clubid")) if str(c).strip())
    return ids


def _is_coupon(row: dict) -> bool:
    flags = {_text(row, "additionaliscoupon")}
    restrictions = row.get("additionalrestrictions")
    if isinstance(restrictions, dict):
        flags.add(_text(restrictions, "additionaliscoupon"))
    return "1" in flags


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return _safe_datetime(value.split(".")[0]) if value else None


def _when(row: dict, dt_key: str, date_key: str, hour_key: str, *, end: bool) -> Optional[datetime]:
    full = _parse_dt(_text(row, dt_key))
    if full:
        return full
    day = _parse_dt(_text(row, date_key))
    if day is None:
        return None
    hour = _text(row, hour_key)
    if hour:
        try:
            parts = [int(p) for p in hour.split(":")[:2]]
            return day.replace(hour=parts[0], minute=parts[1])
        except (ValueError, IndexError):
            pass
    return day.replace(hour=23, minute=59, second=59) if end else day


def _min_qty(raw: Optional[str]) -> Optional[int]:
    qty = _safe_decimal(raw)
    if qty is None or not qty.is_finite() or qty < 1 or qty != qty.to_integral_value():
        return None
    return int(qty)


def normalize_promotion(row: dict, *, as_of: datetime) -> Optional[PromoRecord]:
    """One parsed promotion → PromoRecord, or None when Phase A does not show it."""
    promotion_id = _clean_text(_text(row, "promotionid"), 50)
    description = _clean_text(_text(row, "promotiondescription"), _MAX_DESCRIPTION)
    if not promotion_id or not description:
        return None
    if _CANCELLED in description or description.startswith(_COUPON_PREFIX):
        return None
    if _is_coupon(row) or not _club_ids(row) <= {"0"}:
        return None

    items = _items(row)
    rewards = {_text(row, "rewardtype")} | {_text(i, "rewardtype") for i in items}
    rewards.discard(None)
    if not rewards or not rewards <= ALLOWED_REWARD_TYPES:
        return None

    barcodes: list[str] = []
    for item in items:
        code = _clean_text(_text(item, "itemcode"), 20)
        if code and code not in barcodes:
            barcodes.append(code)
    if not barcodes or len(barcodes) > MAX_ITEMS_PER_PROMOTION:
        return None

    end = _when(row, "promotionenddatetime", "promotionenddate", "promotionendhour", end=True)
    if end is not None and end < as_of:
        return None

    first = items[0] if items else {}
    price = _money(_text(row, "discountedprice") or _text(first, "discountedprice"))
    return PromoRecord(
        promotion_id=promotion_id,
        description=description,
        discounted_price=price if price and price > 0 else None,
        min_qty=_min_qty(_text(row, "minqty") or _text(first, "minqty")),
        start_date=_when(row, "promotionstartdatetime", "promotionstartdate", "promotionstarthour", end=False),
        end_date=end,
        barcodes=barcodes,
    )
```

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v`
Expected: all PASS. If `test_group_layout...` fails on dates, `_safe_datetime` in `app/parser/universal_parser.py` lacks the `%Y-%m-%dT%H:%M:%S` format; the `.split(".")[0]` already strips the milliseconds, so check the failing value rather than adding formats blindly.

- [ ] **Step 5: Commit**

```bash
git add app/parser/promo_loader.py tests/test_promo_loader.py
git commit -m "Promotions: normalise one parsed promotion, dropping what Phase A cannot show"
```

---

### Task 4: `replace_store_promotions` (set-based snapshot load)

**Files:**
- Modify: `app/parser/promo_loader.py` (append)
- Test: `tests/test_promo_loader.py` (append)

**Interfaces:**
- Consumes: `PromoRecord` (Task 3), `Store`, `Product`, `Promotion` models, `settings.PARSE_BATCH_SIZE`.
- Produces:

```python
@dataclass
class PromoLoadStats:
    promotions: int = 0        # records given
    rows_inserted: int = 0     # (promotion, product) rows written
    unknown_barcodes: int = 0  # barcodes with no product, skipped

async def replace_store_promotions(
    session: AsyncSession, store: Store, records: list[PromoRecord]
) -> PromoLoadStats
```

Deletes every promotion row of the store, then inserts the given records, inside the caller's transaction (does not commit).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_promo_loader.py`)

```python
from sqlalchemy import select

from app.db.models import Product, Promotion
from app.parser.promo_loader import PromoRecord, replace_store_promotions


def rec(pid, barcodes, desc="2 ב-18", **over):
    base = dict(promotion_id=pid, description=desc, discounted_price=Decimal("18.00"), min_qty=2,
                start_date=None, end_date=None, barcodes=barcodes)
    base.update(over)
    return PromoRecord(**base)


async def stored(session):
    rows = await session.execute(
        select(Promotion.promotion_id, Product.barcode, Promotion.description)
        .join(Product, Promotion.product_id == Product.id)
        .order_by(Promotion.promotion_id, Product.barcode)
    )
    return rows.all()


async def test_writes_one_row_per_product_and_skips_unknown_barcodes(session, store):
    session.add_all([Product(barcode="111", name="a"), Product(barcode="222", name="b")])
    await session.commit()

    stats = await replace_store_promotions(session, store, [rec("p1", ["111", "222", "999"])])
    await session.commit()

    assert await stored(session) == [("p1", "111", "2 ב-18"), ("p1", "222", "2 ב-18")]
    assert (stats.promotions, stats.rows_inserted, stats.unknown_barcodes) == (1, 2, 1)
    assert (await session.execute(select(Product).where(Product.barcode == "999"))).first() is None


async def test_a_newer_file_replaces_the_stores_old_promotions(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()
    await replace_store_promotions(session, store, [rec("old", ["111"])])
    await session.commit()

    await replace_store_promotions(session, store, [rec("new", ["111"], desc="3 ב-10")])
    await session.commit()

    assert await stored(session) == [("new", "111", "3 ב-10")]


async def test_a_file_with_no_promotions_clears_the_store(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()
    await replace_store_promotions(session, store, [rec("old", ["111"])])
    await session.commit()

    await replace_store_promotions(session, store, [])
    await session.commit()

    assert await stored(session) == []


async def test_the_same_promotion_listed_twice_does_not_break_the_load(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()

    await replace_store_promotions(session, store, [rec("p1", ["111"]), rec("p1", ["111"], desc="again")])
    await session.commit()

    assert await stored(session) == [("p1", "111", "2 ב-18")]   # the first one wins


async def test_other_stores_keep_their_promotions(session, store):
    from app.db.models import Store
    other = Store(chain_id=store.chain_id, store_id="002", name="Other")
    session.add_all([other, Product(barcode="111", name="a")])
    await session.commit()
    await replace_store_promotions(session, other, [rec("keep", ["111"])])
    await session.commit()

    await replace_store_promotions(session, store, [rec("mine", ["111"])])
    await session.commit()

    assert [p for p, _, _ in await stored(session)] == ["keep", "mine"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v -k "writes or replaces or clears or twice or other_stores"`
Expected: FAIL with `ImportError: cannot import name 'replace_store_promotions'`.

- [ ] **Step 3: Implement** (append to `app/parser/promo_loader.py`; extend the imports at the top with the lines shown)

```python
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import settings
from app.db.models import Product, Promotion, Store


@dataclass
class PromoLoadStats:
    promotions: int = 0
    rows_inserted: int = 0
    unknown_barcodes: int = 0


async def replace_store_promotions(
    session: AsyncSession, store: Store, records: list[PromoRecord]
) -> PromoLoadStats:
    """Make `records` the store's whole promotion list. Runs in the caller's transaction."""
    stats = PromoLoadStats(promotions=len(records))
    wanted = sorted({code for record in records for code in record.barcodes})
    product_ids: dict[str, int] = {}
    for start in range(0, len(wanted), settings.PARSE_BATCH_SIZE):
        chunk = wanted[start:start + settings.PARSE_BATCH_SIZE]
        result = await session.execute(select(Product.barcode, Product.id).where(Product.barcode.in_(chunk)))
        product_ids.update(result.all())
    stats.unknown_barcodes = len(wanted) - len(product_ids)

    rows: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for record in records:
        for code in record.barcodes:
            product_id = product_ids.get(code)
            if product_id is None or (record.promotion_id, product_id) in seen:
                continue
            seen.add((record.promotion_id, product_id))
            rows.append({
                "product_id": product_id, "store_id": store.id, "promotion_id": record.promotion_id,
                "description": record.description, "discounted_price": record.discounted_price,
                "min_qty": record.min_qty, "start_date": record.start_date, "end_date": record.end_date,
                "is_active": True,
            })

    await session.execute(delete(Promotion).where(Promotion.store_id == store.id))
    for start in range(0, len(rows), settings.PARSE_BATCH_SIZE):
        await session.execute(insert(Promotion), rows[start:start + settings.PARSE_BATCH_SIZE])
    stats.rows_inserted = len(rows)
    return stats
```

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/parser/promo_loader.py tests/test_promo_loader.py
git commit -m "Promotions: replace a store's promotions from one file, set-based, one transaction"
```

---

### Task 5: Load promo files in `parse_chain`

**Files:**
- Modify: `app/parser/ledger.py` (`record_superseded`), `app/parser/mass_parser.py`
- Test: `tests/xml_samples.py`, `tests/test_parse_chain.py`

**Interfaces:**
- Consumes: `normalize_promotion`, `replace_store_promotions` (Tasks 3-4), `settings.promos_enabled_for` (Task 1).
- Produces: `ledger.record_superseded(session, source_folder, file_names, file_type="price_full")`; `mass_parser.split_superseded(pending, newest_loaded, full_type=FileTypesFilters.PRICE_FULL_FILE)`; `mass_parser._parse_promo_file(dump_file, parser_cls, folder_name) -> tuple[int, int, str]` (rows_total, rows_applied, summary); ledger `file_type` value `"promo_full"`.

Load order inside `parse_chain` becomes: stores, then price files, then promo files (promotions need the products to exist).

- [ ] **Step 1: Add the test builders** (append to `tests/xml_samples.py`)

```python
def promo_xml(store_id: str, promos: list[dict]) -> str:
    """promos: dicts with id, desc, items (barcodes), optional start/end 'YYYY-MM-DD', reward, min_qty, price."""
    body = "".join(
        f"""<Promotion><PromotionId>{p['id']}</PromotionId><AllowMultipleDiscounts>1</AllowMultipleDiscounts>
<PromotionDescription>{p['desc']}</PromotionDescription><PromotionUpdateDate>2026-05-01 12:00</PromotionUpdateDate>
<PromotionStartDate>{p.get('start', '2026-05-01')}</PromotionStartDate><PromotionStartHour>00:00</PromotionStartHour>
<PromotionEndDate>{p.get('end', '2026-12-31')}</PromotionEndDate><PromotionEndHour>23:59</PromotionEndHour>
<IsWeightedPromo>0</IsWeightedPromo><MinQty>{p.get('min_qty', '2.000')}</MinQty><DiscountType>0</DiscountType>
<RewardType>{p.get('reward', '1')}</RewardType><DiscountRate>0</DiscountRate>
<DiscountedPrice>{p.get('price', '18.00')}</DiscountedPrice><MinNoOfItemOfered>10</MinNoOfItemOfered><Remark />
<PromotionItems Count="{len(p['items'])}">{''.join(f'<Item><ItemCode>{c}</ItemCode><ItemType>1</ItemType><IsGiftItem>0</IsGiftItem></Item>' for c in p['items'])}</PromotionItems>
</Promotion>"""
        for p in promos
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?><root>'
        f"<ChainId>{CHAIN}</ChainId><SubChainId>001</SubChainId><StoreId>{store_id}</StoreId>"
        f'<BikoretNo>0</BikoretNo><Promotions>{body}</Promotions></root>'
    )


def promo_name(store: str, stamp: str) -> str:
    """stamp like '20260512-030442' (same shape as price_name)"""
    return f"PromoFull{CHAIN}-001-{store}-{stamp}.xml"
```

- [ ] **Step 2: Write the failing tests** (append to `tests/test_parse_chain.py`; it already imports `settings`, `select`, `write`, `price_name`, `price_xml`, `parse_chain`, and has the `dumps` fixture)

```python
from tests.xml_samples import promo_name, promo_xml


@pytest.fixture
def promos_on(monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_PROMOS", True)
    monkeypatch.setattr(settings, "PROMO_CHAINS", set())


async def stored_promos(session):
    from app.db.models import Promotion
    rows = await session.execute(
        select(Promotion.promotion_id, Product.barcode)
        .join(Product, Promotion.product_id == Product.id)
        .order_by(Promotion.promotion_id, Product.barcode)
    )
    return rows.all()


def good_promos():
    return promo_xml("777", [
        {"id": "p1", "desc": "2 ב-18", "items": ["111", "222"]},
        {"id": "p2", "desc": "מבוטל", "items": ["111"]},                              # cancelled
        {"id": "p3", "desc": "ישן", "items": ["111"], "end": "2026-05-01"},            # already over
        {"id": "p4", "desc": "מתנה", "items": ["111"], "reward": "6"},                 # gift
    ])


async def test_promotions_load_after_prices_and_only_shown_ones_are_kept(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [
        ("111", "5.50", "2026-05-12 01:00"), ("222", "3.30", "2026-05-12 01:00")]))
    name = promo_name("777", "20260512-030500")
    write(dumps, name, good_promos())

    result = await parse_chain("SHUFERSAL")

    assert result.status == "ok" and result.files_ok == 2
    assert await stored_promos(session) == [("p1", "111"), ("p1", "222")]
    assert (await ledger(session))[name] == ("done", 1)


async def test_promo_files_are_ignored_while_promotions_are_off(dumps, session, monkeypatch):
    monkeypatch.setattr(settings, "SCRAPE_PROMOS", False)
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    path = write(dumps, promo_name("777", "20260512-030500"), good_promos())

    result = await parse_chain("SHUFERSAL")

    assert result.files_ok == 1 and path.exists()
    assert await stored_promos(session) == []


async def test_only_the_newest_promo_file_per_store_is_loaded(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    write(dumps, promo_name("777", "20260511-030500"), promo_xml("777", [{"id": "old", "desc": "ישן", "items": ["111"]}]))
    write(dumps, promo_name("777", "20260512-030500"), promo_xml("777", [{"id": "new", "desc": "חדש", "items": ["111"]}]))

    await parse_chain("SHUFERSAL")

    assert await stored_promos(session) == [("new", "111")]
    assert (await ledger(session))[promo_name("777", "20260511-030500")][0] == "superseded"


async def test_a_truncated_promo_file_leaves_the_old_promotions_alone(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    write(dumps, promo_name("777", "20260512-030500"), promo_xml("777", [{"id": "keep", "desc": "2 ב-18", "items": ["111"]}]))
    await parse_chain("SHUFERSAL")

    broken = promo_xml("777", [{"id": "x", "desc": "y", "items": ["111"]}])[:-40]       # cut off
    write(dumps, promo_name("777", "20260513-030500"), broken)
    result = await parse_chain("SHUFERSAL")

    assert result.files_failed == 1
    assert await stored_promos(session) == [("keep", "111")]


async def test_a_promo_file_with_nothing_to_show_clears_the_store(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    write(dumps, promo_name("777", "20260512-030500"), promo_xml("777", [{"id": "p1", "desc": "2 ב-18", "items": ["111"]}]))
    await parse_chain("SHUFERSAL")

    write(dumps, promo_name("777", "20260513-030500"), promo_xml("777", [{"id": "p9", "desc": "מבוטל", "items": ["111"]}]))
    result = await parse_chain("SHUFERSAL")

    assert result.status == "ok"
    assert await stored_promos(session) == []
```

- [ ] **Step 3: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_parse_chain.py -v -k "promo"`
Expected: FAIL (`stored_promos` empty / ledger missing: promo files are not discovered yet). If instead the failure is an exception from `file_name_to_components` or an empty `extracted_store_number`, print `file_name_to_components(str(dumps), promo_name("777", "20260512-030500"))` and adjust `promo_name` in `tests/xml_samples.py` to the shape the library accepts (the real Shufersal file is `PromoFull<chain>-<store>-<12 digits>.xml`), keeping `price_name` untouched.

- [ ] **Step 4: Implement**

In `app/parser/ledger.py` change `record_superseded` to take the file type:

```python
async def record_superseded(
    session: AsyncSession, source_folder: str, file_names: list[str], file_type: str = "price_full"
) -> None:
    """Mark full files as skipped because a newer one for their store is (or was) loaded."""
    for start in range(0, len(file_names), 500):
        stmt = pg_insert(IngestedFile).values([
            {"source_folder": source_folder, "file_name": name, "file_type": file_type,
             "status": SUPERSEDED, "attempts": 0}
            for name in file_names[start:start + 500]
        ])
        await session.execute(stmt.on_conflict_do_nothing(constraint="uq_ingested_files_source_name"))
```

In `app/parser/mass_parser.py`:

1. Imports: `from app.parser.promo_loader import normalize_promotion, replace_store_promotions`.
2. `_FILE_TYPE_LABEL` gains `FileTypesFilters.PROMO_FULL_FILE: "promo_full",`.
3. `split_superseded` takes the kind of full file to keep one-per-store of:

```python
def split_superseded(
    pending: list[DumpFile], newest_loaded: dict[str, datetime],
    full_type: FileTypesFilters = FileTypesFilters.PRICE_FULL_FILE,
) -> tuple[list[DumpFile], list[DumpFile]]:
    """
    Keep only the newest full file of `full_type` per store. A full file is the whole store, so an
    older one for the same store changes nothing the newer one will not overwrite. Returns
    (to_load, skipped). Files of any other type pass through.
    """
```

   and inside replace the two `FileTypesFilters.PRICE_FULL_FILE` comparisons with `full_type`.
4. New loader next to `_parse_price_file`:

```python
async def _parse_promo_file(dump_file: DumpFile, parser_cls, folder_name: str) -> tuple[int, int, str]:
    """Load one PromoFull file as the store's whole promotion list. Returns (rows_total, rows_applied, summary)."""
    if not dump_file.extracted_store_number:
        raise ValueError("file name carries no store number")

    path = Path(dump_file.get_full_path)
    await asyncio.to_thread(assert_well_formed, path)
    parser = parser_cls()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            chain = await get_or_create_chain(
                session, chain_id=dump_file.extracted_chain_id, folder_name=folder_name
            )
            store = await get_or_create_store_from_price_file(
                session, chain, store_id=dump_file.extracted_store_number
            )
            seen = 0
            records = []
            async for row in parser.read(dump_file):
                seen += 1
                record = normalize_promotion(row, as_of=dump_file.extracted_date)
                if record is not None:
                    records.append(record)
            if seen == 0 and path.stat().st_size > _EMPTY_OK_BYTES:
                raise CorruptFile(f"parsed 0 promotions from {path.stat().st_size} bytes")
            stats = await replace_store_promotions(session, store, records)
            await ledger.record_done(
                session, folder_name, dump_file.file_name, "promo_full",
                rows_total=seen, rows_applied=stats.rows_inserted, rows_skipped=seen - len(records),
            )
    summary = (
        f"{seen:,} promotions: {len(records)} shown, {stats.rows_inserted} product rows, "
        f"{stats.unknown_barcodes} unknown barcodes"
    )
    return seen, stats.rows_inserted, summary
```

5. In `parse_chain`:
   - after `wanted_types = (...)` add `if settings.promos_enabled_for(chain_name): wanted_types += (FileTypesFilters.PROMO_FULL_FILE,)`.
   - build `newest_loaded_promo` beside `newest_loaded`: in the ledger loop, entries with `entry.file_type == "promo_full" and entry.status == ledger.DONE` fill a second dict by store (same code as the price branch; refactor the shared lines into a small local helper `remember(target, name)` rather than copying).
   - replace the single `split_superseded` call and its record/delete block with a loop over both kinds:

```python
    pending, old_prices = split_superseded(pending, newest_loaded)
    pending, old_promos = split_superseded(pending, newest_loaded_promo, FileTypesFilters.PROMO_FULL_FILE)
    for label, files in (("price_full", old_prices), ("promo_full", old_promos)):
        if not files:
            continue
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await ledger.record_superseded(session, folder_name, [f.file_name for f in files], label)
        for dump_file in files:
            ledger.delete_loaded_file(folder / dump_file.file_name)
        result.files_skipped += len(files)
        logger.info("%s: %d older %s files skipped (a newer one exists per store)", folder_name, len(files), label)
```

   (Replace the old single `superseded` variable and its record/delete block with this loop; nothing else in `parse_chain` refers to `superseded`.)
   - ordering: replace the sort with a kind rank so promotions come last:

```python
    def _rank(f: DumpFile) -> int:
        return {FileTypesFilters.STORE_FILE: 0, FileTypesFilters.PROMO_FULL_FILE: 2}.get(f.detected_filetype, 1)

    pending.sort(key=lambda f: (_rank(f), _sort_key(f)))
```

   - in the load loop dispatch on the type:

```python
            if is_store:
                _, applied = await _parse_store_file(dump_file, parser_cls, folder_name)
                summary = f"{applied} stores"
            elif dump_file.detected_filetype == FileTypesFilters.PROMO_FULL_FILE:
                _, applied, summary = await _parse_promo_file(dump_file, parser_cls, folder_name)
            else:
                _, applied, summary = await _parse_price_file(dump_file, parser_cls, folder_name)
```

   - the failure path calls `_record_failure`, whose label already comes from `_FILE_TYPE_LABEL` (now includes promo).

- [ ] **Step 5: Run to verify they pass, and nothing else broke**

Run: `venv/bin/python -m pytest tests/test_parse_chain.py tests/test_worker.py tests/test_price_loader.py -v`
Expected: all PASS, including the existing `test_split_superseded_leaves_store_and_delta_files_alone` (default `full_type` keeps its meaning).

- [ ] **Step 6: Commit**

```bash
git add app/parser/ledger.py app/parser/mass_parser.py tests/xml_samples.py tests/test_parse_chain.py
git commit -m "Promotions: load PromoFull files after the price files, newest per store, one transaction"
```

---

### Task 6: API returns active promotions per store

**Files:**
- Modify: `app/api/schemas.py` (new `PromoInfo`, field on `PriceAtStore`), `app/api/routes.py` (`compare_product_prices` + helper)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Promotion` model (Task 2 index; rows from Tasks 4-5).
- Produces: `PromoInfo {description: str, min_qty: int | None, ends_at: datetime | None}`; `PriceAtStore.promotions: list[PromoInfo]` (default `[]`, at most 3 per store, soonest end first, open-ended last).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_api.py`)

```python
async def _promo_fixture(session):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף")
    product = Product(barcode="7290000000111", name="מוצר")
    session.add_all([store, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add(Price(product_id=product.id, store_id=store.id, price=5, price_updated_at=now, is_current=True))
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)

    def promo(pid, desc, start, end):
        return Promotion(product_id=product.id, store_id=store.id, promotion_id=pid, description=desc,
                         min_qty=2, start_date=start, end_date=end, is_active=True)

    session.add_all([
        promo("run", "2 ב-18", local_now - timedelta(days=1), local_now + timedelta(days=3)),
        promo("open", "מבצע פתוח", None, None),
        promo("over", "נגמר", local_now - timedelta(days=9), local_now - timedelta(days=1)),
        promo("later", "עוד לא התחיל", local_now + timedelta(days=1), local_now + timedelta(days=5)),
    ])
    await session.commit()
    return product


async def test_compare_lists_only_running_promotions_soonest_end_first(client, session):
    product = await _promo_fixture(session)
    r = await client.get(f"/api/v1/products/{product.barcode}/compare")
    promos = r.json()["prices"][0]["promotions"]
    assert [p["description"] for p in promos] == ["2 ב-18", "מבצע פתוח"]
    assert promos[0]["min_qty"] == 2 and promos[0]["ends_at"] is not None
    assert promos[1]["ends_at"] is None


async def test_compare_returns_an_empty_promotion_list_when_there_are_none(client, session):
    from datetime import datetime
    from app.db.models import Chain, Price, Product, Store

    chain = Chain(chain_id="1", name="רשת")
    session.add(chain)
    await session.flush()
    store = Store(chain_id=chain.id, store_id="1", name="סניף")
    product = Product(barcode="7290000000112", name="מוצר")
    session.add_all([store, product])
    await session.flush()
    session.add(Price(product_id=product.id, store_id=store.id, price=5, price_updated_at=datetime(2026, 10, 12), is_current=True))
    await session.commit()

    r = await client.get("/api/v1/products/7290000000112/compare")
    assert r.json()["prices"][0]["promotions"] == []


async def test_compare_shows_at_most_three_promotions_per_store(client, session):
    from datetime import datetime
    from app.db.models import Promotion
    product = await _promo_fixture(session)
    store_id = (await session.execute(__import__("sqlalchemy").text("select id from stores limit 1"))).scalar_one()
    session.add_all([
        Promotion(product_id=product.id, store_id=store_id, promotion_id=f"x{i}", description=f"x{i}",
                  start_date=None, end_date=None, is_active=True)
        for i in range(5)
    ])
    await session.commit()
    r = await client.get(f"/api/v1/products/{product.barcode}/compare")
    assert len(r.json()["prices"][0]["promotions"]) == 3
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_api.py -v -k promotion`
Expected: FAIL with `KeyError: 'promotions'`.

- [ ] **Step 3: Implement**

`app/api/schemas.py`, before `PriceAtStore`:

```python
class PromoInfo(BaseModel):
    """A promotion a store runs on a product: the chain's own wording, not a computed price."""
    description: str
    min_qty: Optional[int] = None
    ends_at: Optional[datetime] = None

    @field_validator("ends_at")
    @classmethod
    def _ends_is_utc(cls, v):
        return _israel_to_utc(v)
```

and in `PriceAtStore` add `promotions: List[PromoInfo] = []` after `delivery_url`.

`app/api/routes.py`: add `Promotion` to the `app.db.models` import and `PromoInfo` to the `app.api.schemas` import list, then add above `compare_product_prices`:

```python
MAX_PROMOS_PER_STORE = 3


async def _running_promotions(db: AsyncSession, product_id: int, store_ids: list[int]) -> dict[int, list[PromoInfo]]:
    """Promotions running now (chains publish Israel local time without a zone) per store, soonest end first."""
    now_il = func.timezone("Asia/Jerusalem", func.now())
    rows = await db.execute(
        select(Promotion.store_id, Promotion.description, Promotion.min_qty, Promotion.end_date)
        .where(
            Promotion.product_id == product_id,
            Promotion.store_id.in_(store_ids),
            Promotion.is_active,
            or_(Promotion.start_date.is_(None), Promotion.start_date <= now_il),
            or_(Promotion.end_date.is_(None), Promotion.end_date >= now_il),
        )
        .order_by(Promotion.store_id, Promotion.end_date.asc().nulls_last(), Promotion.promotion_id)
    )
    by_store: dict[int, list[PromoInfo]] = {}
    for store_id, description, min_qty, end_date in rows.all():
        bucket = by_store.setdefault(store_id, [])
        if len(bucket) < MAX_PROMOS_PER_STORE:
            bucket.append(PromoInfo(description=description or "", min_qty=min_qty, ends_at=end_date))
    return by_store
```

In `compare_product_prices`, after the `if not rows:` check add
`promos = await _running_promotions(db, product.id, [store.id for _, store, _ in rows])`
and pass `promotions=promos.get(store.id, []),` to the `PriceAtStore(...)` constructor.

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_api.py -v`
Expected: all PASS (the three new tests and every existing one).

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas.py app/api/routes.py tests/test_api.py
git commit -m "Promotions: product compare returns the promotions running in each store"
```

---

### Task 7: Show promotions in the store row

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/components/StoreRow.tsx`, `frontend/src/pages/ProductPage.tsx`, `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: API field `promotions` (Task 6).
- Produces: `PromoInfo` type; `StoreRow` prop `promo?: string`.

The frontend has no test runner. Verification is `tsc`, a build, and a look in the browser (Step 4).

- [ ] **Step 1: Types.** In `frontend/src/types.ts` add above `PriceAtStore`:

```ts
export interface PromoInfo {
  description: string;
  min_qty?: number;
  ends_at?: string;
}
```

and add `promotions?: PromoInfo[];` as the last field of `PriceAtStore`.

- [ ] **Step 2: `StoreRow`.** Add the prop `promo?: string;` (documented "One-line promotion teaser under the store name") to the props object and its type, and render it right after the `warning` line:

```tsx
          {promo && <div className="store-row-promo" title={promo}>מבצע: {promo}</div>}
```

- [ ] **Step 3: `ProductPage` and CSS.** In the `shownPrices.map` of `ProductPage.tsx` compute, before `return`:

```tsx
                const promos = row.promotions ?? [];
```

pass `promo={promos[0]?.description}` to `<StoreRow ...>`, and inside its children, before the `km` line, add:

```tsx
                    {promos.length > 0 && (
                      <div className="store-row-promos">
                        <div className="store-row-sub">מבצעים ברשת, כפי שהרשת פרסמה (המחיר למעלה הוא מחיר המדף):</div>
                        <ul>
                          {promos.map((p, i) => (
                            <li key={i}>
                              {p.description}
                              {p.ends_at && <span className="store-row-promo-end"> · עד {new Date(p.ends_at).toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric' })}</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
```

Append to `frontend/src/styles/global.css`:

```css
/* Promotions in a store row: one muted line under the name, the full list when the row is open */
.store-row-promo {
  margin-top: 2px; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: var(--fs-12); font-weight: var(--fw-medium); color: var(--orange-700);
}
.store-row-promos { margin-bottom: var(--sp-2); }
.store-row-promos ul { margin: var(--sp-1) 0 0; padding-inline-start: var(--sp-5); font-size: var(--fs-13); color: var(--ink-700); }
.store-row-promo-end { color: var(--ink-400); }
```

(Check the tokens `--fs-12`, `--fs-13`, `--ink-700`, `--ink-400`, `--orange-700`, `--sp-1` exist with `grep -n -e "--fs-12:" -e "--orange-700:" frontend/src/styles/global.css`; if one is missing use the nearest existing token, never a raw colour.)

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit && npx vite build`
Expected: no errors. Then, with local data (Task 8, Step 1) loaded: start the dev server with `preview_start {name: "frontend"}` and the API (`uvicorn main:app --reload`), open a product that has a promotion, and check at mobile width (375×812) that the teaser line ellipsises instead of widening the row, the open row lists the promotions with the "עד dd.mm" date, and a product without promotions looks exactly as before. Stop the server and reset the viewport afterwards.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/components/StoreRow.tsx frontend/src/pages/ProductPage.tsx frontend/src/styles/global.css
git commit -m "Promotions: show the chain's promotion text in the store row"
```

---

### Task 8: Real-data check, docs, rollout notes

**Files:**
- Modify: `docs/deployment.md`, `CLAUDE.md`
- No new tests (this task checks the feature on real files and documents it).

- [ ] **Step 1: Load real Shufersal promotions locally.** The local `dumps/Shufersal` has ~430 promo files from 2026-05-12 and its price files are already in the local ledger.

```bash
SCRAPE_PROMOS=true PROMO_CHAINS=SHUFERSAL venv/bin/python -m app.parser.mass_parser SHUFERSAL
```

Expected: log lines `... promotions: N shown, M product rows, K unknown barcodes` per store and no `failed`. The files in `dumps/` are NOT deleted locally (`DELETE_AFTER_INGEST` is off). Because these files are from May, most promotions have ended: "0 shown" for many stores is correct, not a bug. To see rows on screen, either pick a store whose promotions end after today, or temporarily load with `as_of` far in the past by running one file through `python -c` with a patched `datetime`, then revert; do not commit a patch.

- [ ] **Step 2: Measure.** Report to the user the numbers behind the rollout decision:

```bash
venv/bin/python - <<'EOF'
import asyncio, asyncpg
from dotenv import dotenv_values
u = dotenv_values(".env")["DATABASE_URL"].replace("+asyncpg", "")
async def main():
    c = await asyncpg.connect(u)
    print(await c.fetchval("select count(*) from promotions"), "rows;",
          await c.fetchval("select pg_size_pretty(pg_total_relation_size('promotions'))"),
          "; stores with promotions:", await c.fetchval("select count(distinct store_id) from promotions"))
asyncio.run(main())
EOF
```

Expected: rows and size for the Shufersal stores loaded. Multiply by (production stores of the chain / stores loaded) for a rough per-chain estimate. This is the only evidence for turning on more chains; state it as an estimate.

- [ ] **Step 3: Docs.** In `CLAUDE.md`, in the Parser layer section add one bullet:

```
- `promo_loader.py` + the `PromoFull` path in `mass_parser.py`: loads the chains' promotion files when `SCRAPE_PROMOS` is on (`PROMO_CHAINS` limits it to some chains). Files load after the price files, newest per store, one transaction with the ledger row. `promotions` is a per-store snapshot (each newer full file replaces the store's rows). Only promotions for everybody, reward codes 1/2/3/10, still running, with at most 100 items are kept. Phase A shows the chain's own text; no price is computed from a promotion (reward 6's `DiscountedPrice` is the gift's price).
```

and in the API section note that `/products/{barcode}/compare` rows carry `promotions` (up to 3, running now). In `docs/deployment.md` add a short "Promotions" section: how to turn them on (`SCRAPE_PROMOS=true`, `PROMO_CHAINS=SHUFERSAL,RAMI_LEVY` first), what to watch (`select pg_size_pretty(pg_total_relation_size('promotions'))`, free disk, the cycle duration in `ingest_runs`), and how to turn them off (set `SCRAPE_PROMOS=false`; existing rows stay and are filtered by date, run `TRUNCATE promotions` to clear).

- [ ] **Step 4: Full test run**

Run: `venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/deployment.md CLAUDE.md
git commit -m "Promotions: document the loader, the PROMO_CHAINS switch and the rollout"
```

---

## Rollout (after merge, owned by the user)

1. Deploy with `SCRAPE_PROMOS=false` first: the migration is a cheap index swap on an empty table.
2. Turn on `SCRAPE_PROMOS=true` with `PROMO_CHAINS=SHUFERSAL,RAMI_LEVY`. Watch after the next cycle: table size, free disk, cycle duration, `ingest_runs` errors.
3. Add chains in small groups. The three chains with the most items per store (Tiv Taam, Hazi Hinam, Fresh Market) go last: their files are the biggest.

## Self-Review

- **Coverage:** settings (T1), schema (T2), filter incl. shapes/club/coupon/gift/expired/huge (T3), snapshot load incl. unknown barcodes and duplicates (T4), pipeline incl. order, supersede, truncated and empty files (T5), API incl. active window, empty list, cap (T6), UI (T7), real-data check/docs/rollout (T8). Review Focus 1→T3 `test_a_single_item_arrives_as_a_dict...`; 2→T4 `...listed_twice...`; 3→T5 `...truncated...`, `...nothing_to_show...`; 4→T6; 5→T4 `...unknown_barcodes`.
- **Placeholders:** none. Every code step shows the code.
- **Names:** `PromoRecord`, `normalize_promotion`, `replace_store_promotions`, `PromoLoadStats`, `promos_enabled_for`, `PROMO_CHAINS`, `record_superseded(..., file_type)`, `split_superseded(..., full_type)`, `_parse_promo_file`, `PromoInfo`, `promotions` are used identically across tasks.
- **Known unknowns the executor must check, not assume:** (a) the exact `extracted_store_number` the library derives from the synthetic promo file name (T5 Step 3 says how to adjust); (b) that the library keeps `<Clubs>`/`<AdditionalRestrictions>` children for every chain (the unit tests cover the shapes seen on Rami Levy, Victory and Shufersal files; other chains were not inspected); (c) reward code 3's meaning was not verified against real prices (only 1 and 10 were), which is why Phase A shows text only.
