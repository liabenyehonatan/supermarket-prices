# Promotions, Phase B1 (single-product promotions in the basket) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/basket/compare` prices each basket line with the best "N for X" promotion a store runs on that single product, so a store that is dearer on the shelf can win once the basket quantity triggers its promotion; the basket page shows what the promotion did.

**Architecture:** Phase A's loader decides at load time whether a promotion is safe to compute with (`basket_eligible`: one product, reward code 1 or 10, not weighted/gift/redemption-limited, has `min_qty` and a price) and stores its purchase limit (`max_qty`). A pure function `price_line` turns (shelf price, quantity, promotions) into a line total. The endpoint applies it only for stores whose promotion data is fresh (`stores.last_promo_at` within 7 days), and reports per store `savings` and `promotions_known`, per line the regular total and the promotion used. Club, coupon, multi-product, weighted and gift promotions never change a total.

**Tech Stack:** Python 3.11, SQLAlchemy 2 async, Alembic, FastAPI, pytest (real PostgreSQL `sm_pytest`), React 18 + TypeScript + Vite.

**Spec:** research of this session (no separate spec file). Facts the design rests on, measured on one `PromoFull` file per chain from `dumps/` (May 2026) and the Fourth Schedule of the price-transparency regulations:
- Reward codes 1 and 10 with a single distinct barcode are the "N for X" promotions: Rami Levy 294, Bareket 533, KingStore 252, Tiv Taam 656, Shufersal (store 742) 202 + 54, Victory 446 (code 1) + 4,175 (code 10). `MinQty` = N, `DiscountedPrice` = the price for N units (verified: per-unit promo price is below the shelf price in 39 of 39 code-1 and 345 of 345 code-10 Shufersal items checked against real prices).
- Reward 3 is used by Victory for 3,594 single-product promotions but its meaning was **not** verified, so it stays out of B1.
- Among eligible promotions the flags `AdditionalIsTotal`, `AdditionalIsActive=0`, gift count, minimum purchase were never set; `IsGiftItem=1` appears on 6 of 4,621 Victory rows; `RedemptionLimit` on 10; weighted promos are a minority (Tiv Taam 77 of 656).
- `MaxQty` is a purchase limit: KingStore sets 5/10/15/25 on ~88% of its promotions (`0` = none), Victory/DorAlon send `NO_BODY` (= none), Rami once (`2.00`).
- Shufersal and Victory use code 10 for single-product "N for X"; Shufersal's multi-product code-10 promotions (562 in the sample) are Phase B2.

## Global Constraints

- Money is `Decimal`/`Numeric(10, 2)`, never `float`. All DB access is async (`AsyncSession`). XML keys are lowercase. Stores are chain-scoped.
- Do not weaken Phase A's filters: `normalize_promotion` still returns `None` for club/coupon/cancelled/expired/over-100-item promotions; B1 only adds `basket_eligible`.
- A promotion changes a basket total **only** if `basket_eligible` is true, it is running now (Israel-local dates), and the store's `last_promo_at` is within 7 days. Everything else is shelf price.
- Never mix different promotions on one line; the line takes the single promotion that gives the lowest total (never overstates a saving).
- Never apply a promotion whose per-unit price (`price / min_qty`) is not below the shelf price.
- The basket answer keeps its contract: complete baskets first, then cheapest first; `unit_price` stays the shelf price; `items_missing` is unchanged.
- Schema change = Alembic migration. `api_ro` reads new columns through default privileges.
- Hebrew, RTL, muted look, existing CSS tokens only. Mint stays reserved for "cheapest".
- Branch: `git switch -c promotions-phase-b1 promotions-phase-a` (B1 builds on Phase A's unmerged commits). The working tree holds unrelated uncommitted changes under `docs/planning/`: never `git add -A`/`git add .`; add files by explicit path. Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Push and PR only when the user says so.
- Run tests with `venv/bin/python -m pytest <path> -v` (the `venv/bin/pytest` shebang is broken).

## Review Focus

1. A store whose promotion data was never loaded, or is older than 7 days, must price at shelf price and report `promotions_known: false` (a chain without promo data must not look dearer than one with, but must not get a promotion it no longer runs either).
2. Quantity arithmetic at the edges: quantity below `min_qty`, a remainder after full sets, quantity above `max_qty`, `max_qty` smaller than `min_qty`, `min_qty` = 1 (a plain sale price).
3. Bad data: a promotion whose per-unit price is not below the shelf price, or whose price is 0, must be ignored, not make a line free or dearer.
4. Ranking: with promotion-adjusted totals, complete baskets still rank before incomplete ones and the order is still cheapest first; a dearer-on-the-shelf store can overtake once the quantity triggers its promotion.
5. Multi-product, gift, weighted, redemption-limited and reward-3/other-code promotions must never be `basket_eligible`.

## File Structure

| File | Responsibility |
|---|---|
| `app/basket_promos.py` (create) | `BasketPromo`, `PricedLine`, `price_line` (pure) |
| `migrations/versions/k8a5e1b07d42_promotions_basket_columns.py` (create) | `promotions.basket_eligible/max_qty`, `stores.last_promo_at`, partial index |
| `app/db/models.py` (modify) | the same columns and index |
| `app/parser/promo_loader.py` (modify) | `PromoRecord.basket_eligible/max_qty`, eligibility rules, write the columns |
| `app/parser/mass_parser.py` (modify) | stamp `stores.last_promo_at` after a successful replace |
| `app/api/schemas.py`, `app/api/routes.py` (modify) | basket query, `price_line` per line, `savings`, `promotions_known` |
| `frontend/src/types.ts`, `pages/BasketPage.tsx`, `styles/global.css` (modify) | show the promotion on the line, the saving, the "no promo data" note |
| `tests/test_basket_promos.py` (create); `tests/test_migration.py`, `tests/test_promo_loader.py`, `tests/test_parse_chain.py`, `tests/test_api.py` (modify) | tests |
| `CLAUDE.md`, `docs/deployment.md` (modify) | docs and rollout |

---

### Task 1: `price_line` (pure line pricing)

**Files:**
- Create: `app/basket_promos.py`
- Test: `tests/test_basket_promos.py` (create)

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class BasketPromo:
    promotion_id: str
    description: str
    min_qty: int                 # N units ...
    price: Decimal               # ... cost this much in total
    max_qty: Optional[int]       # most units one purchase can get at the promotion price; None = no limit

@dataclass(frozen=True)
class PricedLine:
    total: Decimal
    regular_total: Decimal
    promo: Optional[BasketPromo] = None
    sets: int = 0                # how many full promotion sets were applied

def price_line(unit_price: Decimal, quantity: int, promos: Sequence[BasketPromo]) -> PricedLine
```

- [ ] **Step 1: Write the failing tests** (`tests/test_basket_promos.py`)

```python
# Pure tests of line pricing: no database.

from decimal import Decimal

from app.basket_promos import BasketPromo, price_line

D = Decimal


def promo(pid="p", n=3, price="10.00", max_qty=None, desc="3 ב-10"):
    return BasketPromo(promotion_id=pid, description=desc, min_qty=n, price=D(price), max_qty=max_qty)


def test_no_promotions_is_the_shelf_price():
    line = price_line(D("4.00"), 3, [])
    assert (line.total, line.regular_total, line.promo, line.sets) == (D("12.00"), D("12.00"), None, 0)


def test_a_full_set_uses_the_promotion():
    line = price_line(D("4.00"), 3, [promo()])
    assert line.total == D("10.00") and line.regular_total == D("12.00")
    assert line.promo.promotion_id == "p" and line.sets == 1


def test_the_remainder_after_full_sets_is_at_shelf_price():
    line = price_line(D("4.00"), 7, [promo()])          # two sets of 3, one left over
    assert line.total == D("24.00") and line.sets == 2


def test_below_the_minimum_quantity_nothing_applies():
    line = price_line(D("4.00"), 2, [promo()])
    assert line.total == D("8.00") and line.promo is None


def test_the_best_of_several_tiers_wins_without_mixing_them():
    tiers = [promo("a", 2, "13.00", desc="2 ב-13"), promo("b", 3, "18.00", desc="3 ב-18"), promo("c", 4, "20.00", desc="4 ב-20")]
    line = price_line(D("7.90"), 5, tiers)
    assert line.promo.promotion_id == "c"
    assert line.total == D("27.90")                      # 4 for 20.00 plus one at 7.90


def test_a_purchase_limit_caps_the_units_that_get_the_promotion():
    line = price_line(D("14.00"), 5, [promo("s", 1, "10.90", max_qty=3, desc="1 ב-10.90")])
    assert line.total == D("60.70") and line.sets == 3   # 3 x 10.90 + 2 x 14.00


def test_a_limit_below_the_set_size_means_no_promotion():
    line = price_line(D("4.00"), 6, [promo(n=3, max_qty=2)])
    assert line.total == D("24.00") and line.promo is None


def test_a_plain_sale_price_is_a_set_of_one():
    line = price_line(D("12.90"), 4, [promo(n=1, price="10.90", desc="1 ב-10.90")])
    assert line.total == D("43.60")


def test_a_promotion_that_is_not_cheaper_per_unit_is_ignored():
    assert price_line(D("3.00"), 3, [promo(price="9.00")]).promo is None     # same as shelf
    assert price_line(D("3.00"), 3, [promo(price="12.00")]).total == D("9.00")  # dearer than shelf


def test_nonsense_promotions_are_ignored():
    for bad in (promo(price="0.00"), promo(n=0)):
        assert price_line(D("4.00"), 3, [bad]).total == D("12.00")


def test_a_tie_between_promotions_is_decided_by_promotion_id():
    twins = [promo("b", desc="second"), promo("a", desc="first")]
    assert price_line(D("4.00"), 3, twins).promo.description == "first"
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_basket_promos.py -v`
Expected: FAIL at import: `ModuleNotFoundError: No module named 'app.basket_promos'`.

- [ ] **Step 3: Implement** (`app/basket_promos.py`)

```python
# app/basket_promos.py
#
# Price one basket line with the best "N for X" promotion of a store (Phase B1).
#
# Deliberately conservative, so a promotion can only ever make a line cheaper than the shelf price by
# an amount the shopper can really get:
#  - one promotion per line (promotions are not mixed: "2 for 13" and "3 for 18" on 5 units is
#    priced with the better single one, repeated, never with a 2 + 3 split)
#  - a promotion that is not below the shelf price per unit is ignored
#  - a purchase limit (max_qty) caps the units that get the promotion price; the rest cost shelf price

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence


@dataclass(frozen=True)
class BasketPromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal
    max_qty: Optional[int]


@dataclass(frozen=True)
class PricedLine:
    total: Decimal
    regular_total: Decimal
    promo: Optional[BasketPromo] = None
    sets: int = 0


def price_line(unit_price: Decimal, quantity: int, promos: Sequence[BasketPromo]) -> PricedLine:
    regular = unit_price * quantity
    best = PricedLine(total=regular, regular_total=regular)
    for promo in sorted(promos, key=lambda p: p.promotion_id):
        if promo.min_qty < 1 or promo.price <= 0 or promo.price >= unit_price * promo.min_qty:
            continue
        covered = quantity if promo.max_qty is None else min(quantity, promo.max_qty)
        sets = covered // promo.min_qty
        if sets == 0:
            continue
        total = sets * promo.price + (quantity - sets * promo.min_qty) * unit_price
        if total < best.total:
            best = PricedLine(total=total, regular_total=regular, promo=promo, sets=sets)
    return best
```

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_basket_promos.py -v`
Expected: 11 PASS.

- [ ] **Step 5: Commit**

```bash
git switch -c promotions-phase-b1 promotions-phase-a
git add app/basket_promos.py tests/test_basket_promos.py
git commit -m "Basket promotions: price one line with the best single N-for-X promotion"
```

---

### Task 2: Columns for eligibility, purchase limit and promo freshness

**Files:**
- Create: `migrations/versions/k8a5e1b07d42_promotions_basket_columns.py`
- Modify: `app/db/models.py` (`Promotion`, `Store`)
- Test: `tests/test_migration.py`

**Interfaces:**
- Produces: `promotions.basket_eligible BOOLEAN NOT NULL DEFAULT false`, `promotions.max_qty INTEGER NULL`, `stores.last_promo_at TIMESTAMP NULL`, partial index `ix_promotions_basket (product_id, store_id) WHERE basket_eligible`; ORM attributes `Promotion.basket_eligible: bool`, `Promotion.max_qty: Optional[int]`, `Store.last_promo_at: Optional[datetime]`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_migration.py`)

```python
async def test_basket_promotion_columns_exist_and_default_to_not_eligible(_database):
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute("TRUNCATE chains RESTART IDENTITY CASCADE")
        await conn.execute("INSERT INTO chains (chain_id, name) VALUES ('1', 'c')")
        await conn.execute("INSERT INTO stores (chain_id, store_id) VALUES (1, 's')")
        await conn.execute("INSERT INTO products (barcode, name) VALUES ('a', 'n')")
        await conn.execute("INSERT INTO promotions (product_id, store_id, promotion_id, is_active) VALUES (1, 1, 'p', true)")
        row = await conn.fetchrow("SELECT basket_eligible, max_qty FROM promotions")
        assert (row["basket_eligible"], row["max_qty"]) == (False, None)
        assert await conn.fetchval("SELECT last_promo_at FROM stores") is None
        index = await conn.fetchval("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_promotions_basket'")
        assert index and "WHERE" in index
    finally:
        await conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `venv/bin/python -m pytest tests/test_migration.py::test_basket_promotion_columns_exist_and_default_to_not_eligible -v`
Expected: FAIL with `UndefinedColumnError: column "basket_eligible" does not exist`.

- [ ] **Step 3: Write the migration**

```python
"""promotions: basket_eligible + max_qty, stores.last_promo_at

Revision ID: k8a5e1b07d42
Revises: j7f4d0a69c31
Create Date: 2026-10-14 15:00:00

Phase B1: the basket prices a line with a promotion only when the loader marked it safe
(basket_eligible), honouring the purchase limit (max_qty), and only for stores whose promotion data is
fresh (last_promo_at). Existing rows stay not eligible until the store's next promotion file replaces them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k8a5e1b07d42"
down_revision: Union[str, None] = "j7f4d0a69c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("promotions", sa.Column("basket_eligible", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("promotions", sa.Column("max_qty", sa.Integer(), nullable=True))
    op.add_column("stores", sa.Column("last_promo_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_promotions_basket", "promotions", ["product_id", "store_id"],
        postgresql_where=sa.text("basket_eligible"),
    )


def downgrade() -> None:
    op.drop_index("ix_promotions_basket", table_name="promotions")
    op.drop_column("stores", "last_promo_at")
    op.drop_column("promotions", "max_qty")
    op.drop_column("promotions", "basket_eligible")
```

In `app/db/models.py`: in `Store` add after `last_full_at`:

```python
    # When this store's last promotion file was loaded. The basket only applies a store's promotions
    # while this is recent: a store that stopped publishing must not keep a promotion that ended.
    last_promo_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
```

in `Promotion` add after `is_active`:

```python
    # Safe to compute a basket price with (one product, "N for X", not weighted/gift/limited by redemptions).
    basket_eligible: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), nullable=False)
    # Most units one purchase can buy at the promotion price (the chain's MaxQty); None = no limit.
    max_qty: Mapped[Optional[int]] = mapped_column(Integer)
```

and to `Promotion.__table_args__` add `Index("ix_promotions_basket", "product_id", "store_id", postgresql_where=text("basket_eligible")),`. (`text` is already imported in `models.py`.)

- [ ] **Step 4: Run to verify it passes**

Run: `venv/bin/python -m pytest tests/test_migration.py -v`
Expected: all PASS (including the existing downgrade/upgrade roundtrip). `venv/bin/python -m alembic heads` prints only `k8a5e1b07d42 (head)`.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/k8a5e1b07d42_promotions_basket_columns.py app/db/models.py tests/test_migration.py
git commit -m "Basket promotions: basket_eligible, max_qty and stores.last_promo_at"
```

---

### Task 3: Decide eligibility in `normalize_promotion`

**Files:**
- Modify: `app/parser/promo_loader.py`
- Test: `tests/test_promo_loader.py`

**Interfaces:**
- Consumes: existing `PromoRecord`, `_items`, `_text`, `_money`, `_min_qty`.
- Produces: `PromoRecord.basket_eligible: bool = False`, `PromoRecord.max_qty: Optional[int] = None` (declared after `barcodes`, so existing constructors keep working).

Eligible means: exactly one distinct barcode; every reward code in `{"1", "10"}`; `min_qty` and `discounted_price` present; not weighted (`isweightedpromo == "1"` or an item `bisweighted == "1"`); no gift flag (`isgiftitem == "1"` on the promotion or an item); no redemption limit (`redemptionlimit` set and not `"0"`); and, when a `max_qty` exists, `max_qty >= min_qty`. `max_qty` is the promotion-level or first item's `maxqty` read as a positive integer (`"0"`, `"NO_BODY"`, empty = no limit).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_promo_loader.py`)

```python
# ── basket eligibility (Phase B1) ─────────────────────────────────────────────

def single(**over):
    """A Rami-Levy-shaped '3 for 10' on one product."""
    return row(promotionitems={"item": [{"itemcode": "111"}]}, minqty="3.00", discountedprice="10.00", **over)


def test_a_single_product_n_for_x_is_basket_eligible():
    rec = normalize_promotion(single(), as_of=AS_OF)
    assert rec.basket_eligible is True and rec.max_qty is None


def test_reward_ten_on_one_product_is_eligible_too():
    assert normalize_promotion(single(rewardtype="10"), as_of=AS_OF).basket_eligible is True


def test_item_level_layout_is_eligible():
    victory = {
        "promotionid": "9", "promotiondescription": "2ב15 ביסקוויט",
        "promotionstartdatetime": "2026-05-04T00:00:00.000", "promotionenddatetime": "2026-12-30T00:00:00.000",
        "clubid": "0", "additionaliscoupon": "0", "redemptionlimit": "",
        "groups": {"group": {"groupid": "1", "promotionitems": {"promotionitem": {
            "itemcode": "7290001", "rewardtype": "10", "minqty": "2", "maxqty": "NO_BODY",
            "discountedprice": "15", "bisweighted": "0"}}}},
    }
    rec = normalize_promotion(victory, as_of=AS_OF)
    assert rec.basket_eligible is True and rec.min_qty == 2 and rec.max_qty is None


@pytest.mark.parametrize("over", [
    {"rewardtype": "3"},                                   # meaning not verified
    {"rewardtype": "2"},                                   # percent: no total price
    {"isweightedpromo": "1"},
    {"isgiftitem": "1"},
    {"redemptionlimit": "2"},
    {"discountedprice": ""},
    {"minqty": "0.50"},                                    # fractional: no whole set
])
def test_what_is_not_a_plain_n_for_x_is_not_eligible(over):
    rec = normalize_promotion(single(**over), as_of=AS_OF)
    assert rec is None or rec.basket_eligible is False


def test_two_products_are_never_eligible():
    rec = normalize_promotion(row(), as_of=AS_OF)              # the default row lists two items
    assert rec is not None and rec.basket_eligible is False


def test_a_weighted_item_is_not_eligible():
    items = {"item": [{"itemcode": "111", "bisweighted": "1"}]}
    assert normalize_promotion(single(promotionitems=items), as_of=AS_OF).basket_eligible is False


@pytest.mark.parametrize("raw, expected", [("5", 5), ("5.00", 5), ("0", None), ("NO_BODY", None), ("", None)])
def test_the_purchase_limit_is_read_as_a_positive_integer(raw, expected):
    assert normalize_promotion(single(maxqty=raw), as_of=AS_OF).max_qty == expected


def test_the_item_level_purchase_limit_is_used_when_the_promotion_has_none():
    items = {"item": [{"itemcode": "111", "maxqty": "10"}]}
    assert normalize_promotion(single(promotionitems=items), as_of=AS_OF).max_qty == 10


def test_a_limit_below_the_set_size_makes_it_not_eligible():
    assert normalize_promotion(single(maxqty="2"), as_of=AS_OF).basket_eligible is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v -k "eligible or purchase_limit or limit_below or weighted_item or two_products"`
Expected: FAIL with `AttributeError: 'PromoRecord' object has no attribute 'basket_eligible'`.

- [ ] **Step 3: Implement.** In `app/parser/promo_loader.py` add to `PromoRecord` (after `barcodes`):

```python
    basket_eligible: bool = False        # safe to compute a basket price with (Phase B1)
    max_qty: Optional[int] = None        # most units one purchase gets at the promotion price
```

add the helpers above `normalize_promotion`:

```python
BASKET_REWARD_TYPES = {"1", "10"}


def _positive_int(raw: Optional[str]) -> Optional[int]:
    """'5', '5.00' -> 5; '0', 'NO_BODY', '' and anything else -> None."""
    value = _safe_decimal(raw)
    if value is None or not value.is_finite() or value < 1 or value != value.to_integral_value():
        return None
    return int(value)


def _basket_eligible(
    row: dict, items: list[dict], rewards: set[str], barcodes: dict, min_qty: Optional[int],
    price: Optional[Decimal], max_qty: Optional[int],
) -> bool:
    """One product, "N for X" (reward 1 or 10), nothing that changes what N units cost at the till."""
    if len(barcodes) != 1 or not rewards <= BASKET_REWARD_TYPES:
        return False
    if min_qty is None or price is None or price <= 0:
        return False
    if _text(row, "isweightedpromo") == "1" or any(_text(i, "bisweighted") == "1" for i in items):
        return False
    if _text(row, "isgiftitem") == "1" or any(_text(i, "isgiftitem") == "1" for i in items):
        return False
    if _text(row, "redemptionlimit") not in (None, "0"):
        return False
    return max_qty is None or max_qty >= min_qty
```

and replace the final `return PromoRecord(...)` of `normalize_promotion` with:

```python
    first = items[0] if items else {}
    price = _money(_text(row, "discountedprice") or _text(first, "discountedprice"))
    price = price if price and price > 0 else None
    min_qty = _min_qty(_text(row, "minqty") or _text(first, "minqty"))
    max_qty = _positive_int(_text(row, "maxqty")) or _positive_int(_text(first, "maxqty"))
    return PromoRecord(
        promotion_id=promotion_id,
        description=description,
        discounted_price=price,
        min_qty=min_qty,
        start_date=_when(row, "promotionstartdatetime", "promotionstartdate", "promotionstarthour", end=False),
        end_date=end,
        barcodes=list(barcodes),
        basket_eligible=_basket_eligible(row, items, rewards, barcodes, min_qty, price, max_qty),
        max_qty=max_qty,
    )
```

(Delete the old `first = ...` / `price = ...` lines that this replaces, so each appears once.)

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v`
Expected: all PASS (the Phase A tests and the new ones).

- [ ] **Step 5: Commit**

```bash
git add app/parser/promo_loader.py tests/test_promo_loader.py
git commit -m "Basket promotions: mark single-product N-for-X promotions as basket eligible"
```

---

### Task 4: Store the new columns and stamp `last_promo_at`

**Files:**
- Modify: `app/parser/promo_loader.py` (`replace_store_promotions` row dict), `app/parser/mass_parser.py` (`_parse_promo_file`)
- Test: `tests/test_promo_loader.py`, `tests/test_parse_chain.py`

**Interfaces:**
- Consumes: `PromoRecord.basket_eligible/max_qty` (Task 3), columns (Task 2).
- Produces: promotion rows carry `basket_eligible` and `max_qty`; `stores.last_promo_at = now()` after a promo file was applied, and **not** touched when the file's items were unreadable (the "keep the old promotions" branch).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_promo_loader.py`:

```python
async def test_the_eligibility_and_the_limit_are_stored(session, store):
    session.add(Product(barcode="111", name="a"))
    await session.commit()

    await replace_store_promotions(session, store, [rec("p1", ["111"], basket_eligible=True, max_qty=5)])
    await session.commit()

    row = (await session.execute(select(Promotion.basket_eligible, Promotion.max_qty))).one()
    assert (row.basket_eligible, row.max_qty) == (True, 5)
```

Append to `tests/test_parse_chain.py`:

```python
async def promo_stamp(session):
    return (await session.execute(select(Store.last_promo_at))).scalar_one()


async def test_a_loaded_promo_file_stamps_the_store(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    write(dumps, promo_name("777", "20260512-030500"), promo_xml("777", [{"id": "p1", "desc": "2 ב-18", "items": ["111"]}]))
    assert await promo_stamp(session) is None

    await parse_chain("SHUFERSAL")

    assert await promo_stamp(session) is not None


async def test_a_file_with_nothing_to_show_still_stamps_the_store(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    write(dumps, promo_name("777", "20260512-030500"), promo_xml("777", [{"id": "p9", "desc": "מבוטל", "items": []}]))

    await parse_chain("SHUFERSAL")

    assert await promo_stamp(session) is not None       # we know this store has no promotions today


async def test_an_unreadable_promo_file_does_not_stamp_the_store(dumps, session, promos_on):
    write(dumps, price_name("777", "20260512-030442"), price_xml("777", [("111", "5.50", "2026-05-12 01:00")]))
    minified = promo_xml("777", [{"id": "p9", "desc": "3 ב-10", "items": ["111"]}]).replace("\n", "")
    write(dumps, promo_name("777", "20260512-030500"), minified)

    await parse_chain("SHUFERSAL")

    assert await promo_stamp(session) is None            # nothing was understood: not "fresh promotion data"
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py tests/test_parse_chain.py -v -k "stored or stamps"`
Expected: FAIL (`basket_eligible` is False/None in the row; `last_promo_at` stays `None`).

- [ ] **Step 3: Implement.** In `replace_store_promotions` add two keys to the row dict:

```python
                "is_active": True,
                "basket_eligible": record.basket_eligible, "max_qty": record.max_qty,
```

In `app/parser/mass_parser.py` extend the imports (`from sqlalchemy import func, update` and `from app.db.models import Store`), and in `_parse_promo_file` stamp the store in the branch that calls `replace_store_promotions` (not in the unreadable branch):

```python
            else:
                stats = await replace_store_promotions(session, store, records)
                await session.execute(update(Store).where(Store.id == store.id).values(last_promo_at=func.now()))
```

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py tests/test_parse_chain.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/parser/promo_loader.py app/parser/mass_parser.py tests/test_promo_loader.py tests/test_parse_chain.py
git commit -m "Basket promotions: store eligibility and limit, stamp stores.last_promo_at"
```

---

### Task 5: `/basket/compare` prices lines with promotions

**Files:**
- Modify: `app/api/schemas.py` (`BasketStoreTotal`), `app/api/routes.py` (`basket_compare`, a shared "running now" clause, a promotion query)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `price_line`, `BasketPromo`, `PricedLine` (Task 1); `Promotion.basket_eligible/max_qty`, `Store.last_promo_at` (Task 2).
- Produces: response per store `savings: Decimal` (regular total minus total, 0 when none) and `promotions_known: bool`; each `item_prices` dict gains `regular_line_total` (Decimal) and `promo` (`null` or `{"description", "min_qty", "price", "sets"}`); `line_total` and `total_price` are promotion-adjusted; `unit_price` is the shelf price.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_api.py`)

```python
async def _basket_world(session, *, promo_age_days=0, eligible=True, max_qty=None, ends_yesterday=False,
                        min_qty=3, promo_price="10.00", shelf_a="4.00", shelf_b="5.00"):
    """Two stores sell one product. A is cheaper on the shelf. B runs '3 for 10' (when eligible)."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, update
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain_a, chain_b = Chain(chain_id="1", name="רשת א"), Chain(chain_id="2", name="רשת ב")
    session.add_all([chain_a, chain_b])
    await session.flush()
    store_a = Store(chain_id=chain_a.id, store_id="1", name="סניף א")
    store_b = Store(chain_id=chain_b.id, store_id="1", name="סניף ב")
    product = Product(barcode="7290000000201", name="חלב")
    session.add_all([store_a, store_b, product])
    await session.flush()
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=product.id, store_id=store_a.id, price=shelf_a, price_updated_at=now, is_current=True),
        Price(product_id=product.id, store_id=store_b.id, price=shelf_b, price_updated_at=now, is_current=True),
    ])
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)
    session.add(Promotion(
        product_id=product.id, store_id=store_b.id, promotion_id="p1", description="3 ב-10",
        min_qty=min_qty, discounted_price=promo_price, max_qty=max_qty, basket_eligible=eligible, is_active=True,
        start_date=local_now - timedelta(days=5),
        end_date=local_now - timedelta(days=1) if ends_yesterday else local_now + timedelta(days=5),
    ))
    await session.commit()
    await session.execute(update(Store).where(Store.id == store_b.id).values(
        last_promo_at=func.now() - timedelta(days=promo_age_days)))
    await session.commit()
    return product


async def _basket(client, qty):
    r = await client.post("/api/v1/basket/compare", json=[{"barcode": "7290000000201", "quantity": qty}])
    assert r.status_code == 200
    return r.json()


def _by_chain(body):
    return {s["store"]["chain"]["name"]: s for s in body["stores"]}


async def test_a_promotion_can_make_the_dearer_shelf_store_win(client, session):
    await _basket_world(session)
    body = await _basket(client, 3)
    assert [s["store"]["chain"]["name"] for s in body["stores"]] == ["רשת ב", "רשת א"]       # B: 10.00 < A: 12.00
    b = _by_chain(body)["רשת ב"]
    assert (float(b["total_price"]), float(b["savings"]), b["promotions_known"]) == (10.0, 5.0, True)
    line = b["item_prices"][0]
    assert float(line["unit_price"]) == 5.0 and float(line["regular_line_total"]) == 15.0
    assert float(line["line_total"]) == 10.0
    assert line["promo"] == {"description": "3 ב-10", "min_qty": 3, "price": "10.00", "sets": 1}
    a = _by_chain(body)["רשת א"]
    assert (float(a["savings"]), a["promotions_known"], a["item_prices"][0]["promo"]) == (0.0, False, None)


async def test_below_the_set_size_the_shelf_price_decides(client, session):
    await _basket_world(session)
    body = await _basket(client, 2)
    assert [s["store"]["chain"]["name"] for s in body["stores"]] == ["רשת א", "רשת ב"]       # 8.00 < 10.00
    assert float(_by_chain(body)["רשת ב"]["savings"]) == 0.0


async def test_the_remainder_and_the_purchase_limit_are_priced_at_shelf(client, session):
    await _basket_world(session, min_qty=1, promo_price="3.00", max_qty=3)
    body = await _basket(client, 5)
    b = _by_chain(body)["רשת ב"]
    assert float(b["total_price"]) == 17.0                  # 3 x 3.00 + 2 x 5.00
    assert b["item_prices"][0]["promo"]["sets"] == 3


async def test_a_store_without_fresh_promotion_data_gets_no_promotion(client, session):
    await _basket_world(session, promo_age_days=8)
    b = _by_chain(await _basket(client, 3))["רשת ב"]
    assert (float(b["total_price"]), b["promotions_known"], b["item_prices"][0]["promo"]) == (15.0, False, None)


async def test_ineligible_or_ended_promotions_never_change_a_total(client, session):
    await _basket_world(session, eligible=False)
    assert float(_by_chain(await _basket(client, 3))["רשת ב"]["total_price"]) == 15.0


async def test_an_ended_promotion_is_not_applied(client, session):
    await _basket_world(session, ends_yesterday=True)
    assert float(_by_chain(await _basket(client, 3))["רשת ב"]["total_price"]) == 15.0


async def test_a_promotion_that_is_not_cheaper_is_ignored(client, session):
    await _basket_world(session, promo_price="15.00")        # 3 for 15.00 = the shelf price
    b = _by_chain(await _basket(client, 3))["רשת ב"]
    assert float(b["total_price"]) == 15.0 and b["item_prices"][0]["promo"] is None


async def test_complete_baskets_still_rank_before_incomplete_ones_with_promotions(client, session):
    from datetime import datetime
    from sqlalchemy import select
    from app.db.models import Chain, Price, Product, Store

    await _basket_world(session)                              # A: 4.00, B: 5.00 with "3 for 10"
    milk = (await session.execute(select(Product).where(Product.barcode == "7290000000201"))).scalar_one()
    bread = Product(barcode="7290000000202", name="לחם")
    chain_c = Chain(chain_id="3", name="רשת ג")
    session.add_all([bread, chain_c])
    await session.flush()
    store_c = Store(chain_id=chain_c.id, store_id="1", name="סניף ג")
    session.add(store_c)
    await session.flush()
    stores = {s.name: s for s in (await session.execute(select(Store))).scalars().all()}
    now = datetime(2026, 10, 12)
    session.add_all([
        Price(product_id=bread.id, store_id=stores["סניף א"].id, price="1.00", price_updated_at=now, is_current=True),
        Price(product_id=bread.id, store_id=stores["סניף ב"].id, price="1.00", price_updated_at=now, is_current=True),
        Price(product_id=milk.id, store_id=store_c.id, price="1.00", price_updated_at=now, is_current=True),   # C has no bread
    ])
    await session.commit()

    r = await client.post("/api/v1/basket/compare", json=[
        {"barcode": "7290000000201", "quantity": 3}, {"barcode": "7290000000202", "quantity": 1}])
    stores_out = r.json()["stores"]
    assert [(s["store"]["chain"]["name"], s["items_missing"]) for s in stores_out] == [
        ("רשת ב", 0), ("רשת א", 0), ("רשת ג", 1)]               # B 11.00 (promotion), A 13.00, then the cheap incomplete C
    assert [float(s["total_price"]) for s in stores_out] == [11.0, 13.0, 3.0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_api.py -v -k "promotion or remainder or fresh or rank_before"`
Expected: FAIL with `KeyError: 'savings'` (or `promotions_known`).

- [ ] **Step 3: Implement.**

`app/api/schemas.py`, in `BasketStoreTotal` add after `item_prices`:

```python
    # What the promotions took off this store's shelf total (0 when none applied), and whether we hold
    # fresh promotion data for it (a store without it is priced at shelf price, which may be too high).
    savings: Decimal = Decimal("0")
    promotions_known: bool = False
```

`app/api/routes.py`: add the import `from app.basket_promos import BasketPromo, price_line`. Add, next to `_running_promotions`, a shared clause and the basket query, and make `_running_promotions` use the clause:

```python
PROMO_FRESH_DAYS = 7      # a store's promotions count only if its promotion file was loaded this recently


def _running_now():
    """The promotion is inside its dates now (chains publish Israel local time without a zone)."""
    now_il = func.timezone("Asia/Jerusalem", func.now())
    return and_(
        Promotion.is_active,
        or_(Promotion.start_date.is_(None), Promotion.start_date <= now_il),
        or_(Promotion.end_date.is_(None), Promotion.end_date >= now_il),
    )


async def _basket_promotions(db: AsyncSession, product_ids: list[int]) -> dict[tuple[int, int], list[BasketPromo]]:
    """Promotions safe to price a basket with, running now, per (store, product)."""
    rows = await db.execute(
        select(
            Promotion.store_id, Promotion.product_id, Promotion.promotion_id, Promotion.description,
            Promotion.min_qty, Promotion.discounted_price, Promotion.max_qty,
        ).where(
            Promotion.product_id.in_(product_ids),
            Promotion.basket_eligible,
            Promotion.min_qty.is_not(None),
            Promotion.discounted_price.is_not(None),
            _running_now(),
        )
    )
    by_line: dict[tuple[int, int], list[BasketPromo]] = {}
    for store_id, product_id, promotion_id, description, min_qty, price, max_qty in rows.all():
        by_line.setdefault((store_id, product_id), []).append(
            BasketPromo(promotion_id, description or "", min_qty, price, max_qty))
    return by_line
```

Rewrite the body of `_running_promotions`'s `where(...)` to `Promotion.product_id == product_id, Promotion.store_id.in_(store_ids), _running_now(),` (drop its local `now_il` and the two `or_` lines).

In `basket_compare`:

1. Add to the `prices_query` select list: `func.coalesce(Store.last_promo_at >= func.now() - timedelta(days=PROMO_FRESH_DAYS), False).label("promo_known"),` (after `Store.longitude`).
2. After `all_price_rows = ...` add `promos_by_line = await _basket_promotions(db, list(by_id)) if by_id else {}`.
3. In Step 4, replace the `entry[1][product.barcode] = {...}` assignment with:

```python
        line = price_line(
            r.price, qty, promos_by_line.get((r.store_pk, r.product_id), []) if r.promo_known else [])
        entry[1][product.barcode] = {
            "product_name": product.name,
            "barcode": product.barcode,
            "unit_price": r.price,
            "quantity": qty,
            "line_total": line.total,
            "regular_line_total": line.regular_total,
            "promo": None if line.promo is None else {
                "description": line.promo.description, "min_qty": line.promo.min_qty,
                "price": line.promo.price, "sets": line.sets,
            },
        }
```

4. In Step 5 keep `total = sum(line_total)` (now promotion-adjusted) and carry the savings: change `ranked.append((missing, total, r, items))` to also compute
   `savings = sum((i["regular_line_total"] - i["line_total"] for i in items_by_barcode.values()), Decimal("0"))`, keep the sort key `(missing, total)`, and in Step 6 pass `savings=savings, promotions_known=bool(r.promo_known),` to `BasketStoreTotal.model_construct(...)`. Update the tuple unpacking in the `complete_totals`, `max_total`, `cheapest_store` lines and in the Step 6 comprehension to the new tuple shape `(missing, total, savings, r, items_by_barcode)`.

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_api.py -v`
Expected: all PASS (new and existing, including `test_basket_limit_keeps_the_best_stores_and_reports_the_totals`).

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas.py app/api/routes.py tests/test_api.py
git commit -m "Basket promotions: price basket lines with single-product N-for-X promotions"
```

---

### Task 6: Show it on the basket page

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/pages/BasketPage.tsx`, `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: API fields from Task 5.
- Produces: `ItemPromo` type; `ItemPrice.regular_line_total/promo`; `BasketStoreTotal.savings/promotions_known`.

No frontend test runner exists: verification is `tsc`, a build and the browser check in Step 4.

- [ ] **Step 1: Types** (`frontend/src/types.ts`). Above `ItemPrice` add:

```ts
export interface ItemPromo {
  description: string;
  min_qty: number;
  price: number | string;
  sets: number;
}
```

and add to `ItemPrice`: `regular_line_total?: number | string; promo?: ItemPromo | null;` and to `BasketStoreTotal`: `savings?: number | string; promotions_known?: boolean;`.

- [ ] **Step 2: Result card** (`BasketPage.tsx`, `ResultCard`). In the breakdown row replace the name/line block with:

```tsx
        {store.item_prices.map((item, i) => (
          <div key={i} className="basket-breakdown-row">
            <div className="basket-breakdown-name" title={item.product_name}>
              {item.product_name}
              {item.quantity > 1 && (
                <span style={{ color: 'var(--ink-400)', marginInlineStart: 4 }}>×{item.quantity}</span>
              )}
              {item.promo && (
                <div className="basket-breakdown-promo">מבצע: {item.promo.description}{item.promo.sets > 1 ? ` (×${item.promo.sets})` : ''}</div>
              )}
            </div>
            {item.missing
              ? <span className="basket-breakdown-missing">לא זמין</span>
              : <span className="basket-breakdown-line tabular">
                  {item.promo && item.regular_line_total != null && (
                    <s className="basket-breakdown-was">{fmt(item.regular_line_total)}</s>
                  )}
                  {fmt(item.line_total)}
                </span>
            }
          </div>
        ))}
```

Before the `סה״כ` row add:

```tsx
        {promoSavings > 0.005 && (
          <div className="basket-breakdown-row basket-breakdown-saving">
            <div className="basket-breakdown-name">הסכום כולל מבצעים</div>
            <span className="basket-breakdown-line tabular">חיסכון {fmt(promoSavings)}</span>
          </div>
        )}
        {store.promotions_known === false && (
          <div className="store-row-sub basket-no-promo">אין לנו נתוני מבצעים לסניף הזה, ייתכן שהמחיר בפועל נמוך יותר.</div>
        )}
```

and define `const promoSavings = Number(store.savings ?? 0);` beside the existing `savings` constant.

- [ ] **Step 3: Page note and CSS.** In the results block, right after `<CompareDelta .../>`:

```tsx
            {results.stores.some(s => s.promotions_known) && (
              <div className="basket-promo-note">
                הסכומים כוללים מבצעי &quot;N ב-X&quot; על מוצר בודד, בסניפים שיש לנו עבורם נתוני מבצעים. מבצעי מועדון, קופונים ומבצעים על כמה מוצרים יחד לא נכללים.
              </div>
            )}
```

Append to `global.css`:

```css
/* Basket promotions: the promotion under the item name, the shelf total struck through, the saving row */
.basket-breakdown-promo { margin-top: 2px; font-size: var(--fs-12); font-weight: var(--fw-medium); color: var(--orange-700); }
.basket-breakdown-was { margin-inline-end: var(--sp-2); color: var(--ink-400); font-weight: var(--fw-medium); }
.basket-breakdown-saving { background: var(--orange-50); color: var(--orange-700); }
.basket-no-promo { padding: var(--sp-2) var(--sp-4); color: var(--ink-400); }
.basket-promo-note { margin-bottom: var(--sp-3); font-size: var(--fs-12); color: var(--ink-400); }
```

(Check `--orange-50` exists: `grep -n -e "--orange-50:" frontend/src/styles/global.css`; if not, use `--surface-50`.)

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit && npx vite build`
Expected: no errors. Then, with the Task 7 demo database running (`API` on 8011, `frontend-demo` preview on 3011): at 375 px add the demo product to the basket with quantity 3, open the basket page (`/#/basket`), press compare; expect the saving row, the struck-through shelf total, "מבצע: …" under the item, the page note, and for the second demo store the "no promotion data" line. Check no horizontal overflow and that a basket with no promotions looks exactly as before. Reset the viewport, stop the preview and revert the temporary `.claude/launch.json` entry afterwards.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/BasketPage.tsx frontend/src/styles/global.css
git commit -m "Basket promotions: show the promotion, the saving and the missing-data note"
```

---

### Task 7: Real-data demo, docs, rollout

**Files:**
- Modify: `CLAUDE.md`, `docs/deployment.md`

- [ ] **Step 1: Demo database with real files.** Never touch the user's dev database (it is at an older schema). Use a throwaway one:

```bash
S=<scratchpad>; mkdir -p $S/demo/dumps/Shufersal
cp dumps/Shufersal/PriceFull7290027600007-742-202602190300.xml dumps/Shufersal/PromoFull7290027600007-742-202602190300.xml dumps/Shufersal/Stores7290027600007-000-202605120201.xml $S/demo/dumps/Shufersal/
export DATABASE_URL=<.env URL with database name sm_promo_demo> DUMPS_DIR=$S/demo/dumps SCRAPE_PROMOS=true PROMO_CHAINS=SHUFERSAL DELETE_AFTER_INGEST=false
# create the empty database sm_promo_demo, then:
venv/bin/python -m alembic upgrade head
venv/bin/python -m app.parser.mass_parser SHUFERSAL
```

Give store 742 a name and city (`UPDATE stores SET name='שופרסל דיל דוגמה', city='תל אביב' WHERE store_id='742'`) or the page hides it. Check which promotions became eligible: `SELECT count(*) FILTER (WHERE basket_eligible), count(*) FROM promotions;` and pick a product with an eligible, still-running promotion (end date after today). Add a second store for the ranking effect: insert a store in another chain with the same product at a slightly lower shelf price and no promotions (it gets `promotions_known = false`). Start the API on a free port (8000 may be the user's own server) with `FRONTEND_URL=http://localhost:3011`, and a temporary `frontend-demo` entry in the git-ignored `.claude/launch.json` (`env VITE_API_URL=http://localhost:8011 PORT=3011 npm run dev --prefix frontend`). The app uses a hash router: open `http://localhost:3011/#/product/<barcode>`.

- [ ] **Step 2: Document.** In `CLAUDE.md` replace the `/basket/compare` bullet's description with: "total cost of a list of `{barcode, quantity}` items per store, sorted cheapest first. A line is priced with the best single-product 'N for X' promotion (`promotions.basket_eligible`, reward codes 1/10) only for stores whose `last_promo_at` is within 7 days; `unit_price` is the shelf price, `line_total` is promotion-adjusted, each store reports `savings` and `promotions_known`." In the Rules section add:

```
**A promotion changes a basket total only when it is `basket_eligible`.** One product, reward 1 or 10, not weighted/gift/redemption-limited, running now, and the store's promotion data is fresh. Promotions are never mixed on one line and one that is not below the shelf price per unit is ignored (`app/basket_promos.py`). Club, coupon, multi-product and reward-3 promotions stay display-only.
```

In `docs/deployment.md`, in the Promotions section add: after deploying, `basket_eligible` fills only as each store's next promotion file loads (the first cycle); check `select count(*) filter (where basket_eligible), count(*) from promotions;`; and sanity-check the biggest discounts to catch a mis-read promotion: `select p.barcode, pr.description, pr.min_qty, pr.discounted_price, price.price from promotions pr join products p on p.id = pr.product_id join prices price on price.product_id = pr.product_id and price.store_id = pr.store_id and price.is_current where pr.basket_eligible and pr.discounted_price / pr.min_qty < 0.4 * price.price limit 50;`. Note that totals now drop when promotions are on, so the basket page's "last time" comparison shows the first promotion-priced comparison as a price drop.

- [ ] **Step 3: Full test run**

Run: `venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/deployment.md
git commit -m "Basket promotions: document the rule, the demo procedure and the rollout checks"
```

---

## Rollout (after merge, owned by the user)

1. Merge Phase A first (B1 sits on top of it), then B1. The migration is cheap: two columns, one nullable column, one partial index on a table that is empty until promotions are turned on.
2. With promotions already on for some chains, `basket_eligible` stays false until each store's next promotion file loads; the first cycle after deploy fills it.
3. Run the sanity query from `docs/deployment.md` after the first cycle; a promotion that cuts the per-unit price by more than 60% deserves a look at its raw XML before more chains are switched on.
4. Phase B2 (multi-product promotions, Shufersal's reward-10 groups) is separate: it needs the quantities of several products pooled across one promotion.

## Self-Review

- **Coverage:** line pricing (T1), schema (T2), eligibility rules incl. reward 10, limits, weighted/gift/redemption (T3), storage + freshness stamp incl. "unreadable file does not stamp" (T4), API incl. ranking flip, remainder/limit, stale data, ineligible, ended, not-cheaper, incomplete-basket order (T5), UI (T6), demo/docs/rollout (T7). Review Focus 1→T5 stale test; 2→T1 + T5 remainder/limit; 3→T1 + T5 not-cheaper; 4→T5 flip and incomplete ordering; 5→T3 parametrized.
- **Placeholders:** none; the only angle-bracket values are environment paths in the manual demo commands of T7 Step 1 (scratchpad directory, database URL), which depend on the machine.
- **Names:** `BasketPromo`, `PricedLine`, `price_line`, `basket_eligible`, `max_qty`, `last_promo_at`, `savings`, `promotions_known`, `regular_line_total`, `promo`, `PROMO_FRESH_DAYS`, `_running_now`, `_basket_promotions` are used identically across tasks.
- **Known unknowns the executor must check, not assume:** (a) in T5 the exact tuple shape change in `basket_compare` (the `ranked` tuples are unpacked in four places: re-read the function before editing); (b) `--orange-50` token; (c) reward code 3 stays out because its meaning is unverified; (d) whether the database session timezone is UTC (`last_promo_at` is written with `now()` like `last_full_at`, and compared with `now()` in SQL, so it is consistent either way); (e) the shelf-price remainder assumes a chain applies at most the sets that fit, which matches how the regulation defines the minimum-quantity condition but was not checked against a till.
