# Promotions, Phase B2 (multi-product "N for X" promotions in the basket) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/basket/compare` also prices promotions that cover several products ("any 3 of these 4 for 10", "3 books for 100"): the quantities of the promotion's products in the basket are pooled, as many full sets as fit get the promotion price, the rest stays at shelf price.

**Architecture:** The loader's `basket_eligible` rule is widened from "one product" to "one product, or a product group whose price the promotion text confirms". A new engine `price_store` replaces the per-line `price_line` for the basket: per store it picks promotions greedily by total saving, lets a product belong to at most one promotion, and allocates a group's sets to the *cheapest* units first (so a saving is never overstated). A single-product result keeps B1's per-line representation; a multi-product result is returned as a store-level `promo_adjustments` entry that is subtracted from the total. `price_line` stays as a thin wrapper over the engine so B1's tests keep guarding the single-product behaviour. No migration: the columns exist.

**Tech Stack:** Python 3.11, SQLAlchemy 2 async, FastAPI, pytest (real PostgreSQL `sm_pytest`), React 18 + TypeScript + Vite.

**Spec:** research of this session (no separate spec file). Facts the design rests on, measured on one `PromoFull` file per chain from `dumps/` (May 2026) and, for prices, on the local copy of Shufersal's price files:
- Promotions that list several products with reward code 1 or 10 and pass the other filters: 9,115 across chains; **5,806 (64%) have a description that states "N ב-price" with the file's own N and price** (e.g. "3ב10", "מבצע ספרים 3 ב-100"). Most of the rest are `MinQty 1` ones ("...-ב16.90": a sale price for each of several variants) and ones written as "2 יח ב 20".
- Only 11 promotions of those use more than one `<Group>` (buy from group A *and* group B): they must not be pooled. 3 have item-level prices that differ.
- Against real shelf prices in about 100 Shufersal stores: of 14,915 group promotions with at least N known products, **14,668 (98%) save money** (price is 0.25 to 1.00, median 0.78 of the N cheapest products' shelf total). The 247 that do not are "% הנחה" promotions coded as reward 1 with `MinQty 1` whose stored price is not a sale price; their text has no "ב-price", so confirmation drops them.
- "Any N of the group" is the regulation's definition of reward code 10 ("אוסף מוצרים בהנחה"); this was not checked against a till.

## Global Constraints

- Money is `Decimal`/`Numeric(10, 2)`, never `float`. All DB access async. XML keys lowercase. Stores chain-scoped.
- Never overstate a saving: a promotion is applied only if every set it takes saves money; group sets take the cheapest units first; a product is covered by at most one promotion per store; promotions are never mixed on one product.
- A group promotion (more than one product in the file) is `basket_eligible` only if: reward codes ⊆ {1, 10}, a single `<Group>` (or the flat layout), item-level prices agree, not weighted/gift/redemption-limited, `min_qty` and price present, `max_qty >= min_qty` when set, **and `price_is_total` is true** (the text confirms the price; for `min_qty` 1 the text must show "ב-price" with the same price).
- Single-product behaviour stays exactly as in B1 (every existing B1 test must keep passing, except the one test this plan replaces and says so).
- The basket answer keeps its contract: complete baskets first, then cheapest first; `unit_price` stays the shelf price; `items_missing` unchanged; a store without fresh promotion data (`promotions_known` false) gets no promotion.
- Hebrew, RTL, muted look, existing CSS tokens only. Mint stays reserved for "cheapest".
- Branch: `git switch -c promotions-phase-b2 promotions-phase-b1` (B2 builds on B1's unmerged commits). Unrelated uncommitted changes sit under `docs/planning/`: never `git add -A` / `git add .`; add files by explicit path. Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Push and PR only when the user says so.
- Run tests with `venv/bin/python -m pytest <path> -v` (the `venv/bin/pytest` shebang is broken).

## Review Focus

1. A saving that cannot be had at the till: one unit used by two promotions, one product under two promotions, a set that saves nothing taken anyway, group sets allocated to expensive units first.
2. Pooling edges: fewer units of the group's products in the basket than `min_qty` (no promotion), remainder units, several full sets, a purchase limit across the group, `min_qty` 1 groups (a per-unit sale price: only units dearer than the price get it).
3. An N>1 group whose price the text does not confirm (it may be a per-unit price), a multi-`<Group>` promotion, differing item-level prices, weighted/gift/limited, and "% הנחה" promotions coded as reward 1: none may be eligible.
4. Priority between promotions: the one with the largest total saving wins a shared product, and a disjoint promotion still applies next to it; tiers on one product behave as in B1.
5. Cost: the promotion query is restricted to the stores in the answer, the engine runs only for stores that have promotions, and a 100-item basket over ~2,000 stores stays fast.

## File Structure

| File | Responsibility |
|---|---|
| `app/parser/promo_loader.py` (modify) | confirmation regexes, group detection, widened `_basket_eligible` |
| `app/basket_promos.py` (modify) | `StorePromo`, `AppliedPromo`, `price_store`; `price_line` becomes a wrapper |
| `app/api/routes.py`, `app/api/schemas.py` (modify) | per-store promotion query, engine call, `promo_adjustments`, totals |
| `frontend/src/types.ts`, `pages/BasketPage.tsx`, `styles/global.css` (modify) | show group promotions in the store card |
| `tests/test_promo_loader.py`, `tests/test_basket_promos.py`, `tests/test_api.py` (modify) | tests |
| `CLAUDE.md`, `docs/deployment.md` (modify) | rule and rollout |

---

### Task 1: Group promotions can be `basket_eligible`

**Files:**
- Modify: `app/parser/promo_loader.py`
- Test: `tests/test_promo_loader.py`

**Interfaces:**
- Consumes: existing `_text`, `_items`, `_as_list`, `PromoRecord`, `_positive_int`.
- Produces: `_price_is_total` also accepts "2 יח ב 20" and, for `min_qty == 1`, any "ב-price" equal to the price; `_group_count(row) -> int`; `_basket_eligible(..., price_is_total)` accepts multi-product promotions that meet the Global Constraints list.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_promo_loader.py`)

```python
# ── group promotions (Phase B2) ───────────────────────────────────────────────

def group(**over):
    """A Rami-Levy-shaped '3 for 10' on four products, text confirms the price."""
    base = dict(
        promotiondescription="פטרוזליה/כוסברה/שמיר/נענע 3ב10", minqty="3.00", discountedprice="10.00",
        promotionitems={"item": [{"itemcode": c} for c in ("111", "222", "333", "444")]},
    )
    base.update(over)
    return row(**base)


def test_a_group_promotion_whose_text_confirms_the_price_is_eligible():
    rec = normalize_promotion(group(), as_of=AS_OF)
    assert rec.basket_eligible is True and rec.price_is_total is True and len(rec.barcodes) == 4


def test_a_group_promotion_whose_text_does_not_confirm_the_price_is_not_eligible():
    rec = normalize_promotion(group(promotiondescription="מבצע ירקות"), as_of=AS_OF)
    assert rec is not None and rec.basket_eligible is False


@pytest.mark.parametrize("over", [
    {"promotionitems": {"item": [{"itemcode": "1", "discountedprice": "10"}, {"itemcode": "2", "discountedprice": "12"}]}},
    {"isweightedpromo": "1"},
    {"isgiftitem": "1"},
    {"redemptionlimit": "2"},
    {"rewardtype": "3"},
    {"maxqty": "2"},                                          # below the set size of 3
])
def test_group_promotions_with_anything_unsafe_are_not_eligible(over):
    rec = normalize_promotion(group(**over), as_of=AS_OF)
    assert rec is None or rec.basket_eligible is False


def test_a_promotion_spread_over_several_groups_is_never_pooled():
    two_groups = {"group": [
        {"groupid": "1", "promotionitems": {"promotionitem": {"itemcode": "111"}}},
        {"groupid": "2", "promotionitems": {"promotionitem": {"itemcode": "222"}}},
    ]}
    rec = normalize_promotion(group(promotionitems=None, groups=two_groups), as_of=AS_OF)
    assert rec is not None and rec.basket_eligible is False


def test_a_single_group_in_the_group_layout_is_pooled():
    one_group = {"group": {"groupid": "1", "promotionitems": {"promotionitem": [
        {"itemcode": "111"}, {"itemcode": "222"}]}}}
    rec = normalize_promotion(group(promotionitems=None, groups=one_group), as_of=AS_OF)
    assert rec.basket_eligible is True


def test_a_one_unit_sale_price_for_a_group_needs_the_text_to_show_that_price():
    ok = normalize_promotion(group(promotiondescription="פסטה/ריגטי-ב12.90", minqty="1", discountedprice="12.90"), as_of=AS_OF)
    assert ok.basket_eligible is True
    percent = normalize_promotion(group(promotiondescription="בי 40% הנחה לוריאל", minqty="1", discountedprice="36.90"), as_of=AS_OF)
    assert percent.basket_eligible is False
    unlabelled = normalize_promotion(group(promotiondescription="יין לבן ברקן", minqty="1", discountedprice="34.90"), as_of=AS_OF)
    assert unlabelled.basket_eligible is False


@pytest.mark.parametrize("description, minqty, price, expected", [
    ("מבצע שלגון תמרה 2 יח ב 20 שח", "2.00", "20.00", True),
    ("מנה חמה נודלס 3 יח' ב 24 שח", "3.00", "24.00", True),
    ("נוזל רצפות אולטרה ב10", "1.00", "10.00", True),
    ("פסטה פטוצ'יני-ב12.90", "1.00", "12.90", True),
    ("נוזל רצפות ב10", "2.00", "10.00", False),            # a bare "ב10" confirms nothing when N is 2
    ("בי 40% הנחה לוריאל", "1.00", "36.90", False),
    ("יין לבן ברקן 750 מ\"ל", "1.00", "34.90", False),
])
def test_more_wordings_of_the_total_are_recognised(description, minqty, price, expected):
    rec = normalize_promotion(single(promotiondescription=description, minqty=minqty, discountedprice=price), as_of=AS_OF)
    assert rec.price_is_total is expected
```

And replace the Phase B1 test `test_two_products_are_never_eligible` (B2 supersedes it: two products ARE eligible once the text confirms the price) with:

```python
def test_two_products_are_eligible_only_with_a_confirmed_price():
    unconfirmed = normalize_promotion(row(promotiondescription="מבצע"), as_of=AS_OF)   # the default row lists two items
    assert unconfirmed is not None and unconfirmed.basket_eligible is False
    confirmed = normalize_promotion(row(), as_of=AS_OF)                              # description "2 ב-18", MinQty 2, price 18
    assert confirmed.basket_eligible is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py -v -k "group or two_products or wordings"`
Expected: FAIL (group promotions come back `basket_eligible False`; "2 יח ב 20" not recognised).

- [ ] **Step 3: Implement.** In `app/parser/promo_loader.py` replace `_N_FOR_X` and `_price_is_total` with:

```python
_N_FOR_X = re.compile(r"(\d+)\s*(?:יח(?:ידות|['׳])?\s*)?ב\s*-?\s*(\d+(?:\.\d+)?)")
_FOR_X = re.compile(r"(?<!\w)ב\s*-?\s*(\d+(?:\.\d+)?)")


def _price_is_total(description: str, min_qty: Optional[int], price: Optional[Decimal]) -> bool:
    """The text says "2ב18" / "2 יח ב 20" and the file says MinQty 2, price 18: two independent fields agree
    that the price is the total for N units. For one unit a bare "-ב12.90" with the same price is enough."""
    if min_qty is None or price is None:
        return False
    if any(int(n) == min_qty and Decimal(x) == price for n, x in _N_FOR_X.findall(description)):
        return True
    return min_qty == 1 and any(Decimal(x) == price for x in _FOR_X.findall(description))
```

add above `_basket_eligible`:

```python
def _group_count(row: dict) -> int:
    """How many <Group> elements the promotion has (0 for the flat layout)."""
    groups = row.get("groups")
    return len(_as_list(groups.get("group"))) if isinstance(groups, dict) else 0
```

and replace `_basket_eligible` and its call with:

```python
def _basket_eligible(
    row: dict, items: list[dict], rewards: set[str], barcodes: dict, min_qty: Optional[int],
    price: Optional[Decimal], max_qty: Optional[int], price_is_total: bool,
) -> bool:
    """"N for X" (reward 1 or 10) on one product, or on a group of products when the text confirms the
    price; nothing that changes what N units cost at the till."""
    if not barcodes or not rewards <= BASKET_REWARD_TYPES:
        return False
    if min_qty is None or price is None or price <= 0:
        return False
    if _text(row, "isweightedpromo") == "1" or any(_text(i, "bisweighted") == "1" for i in items):
        return False
    if _text(row, "isgiftitem") == "1" or any(_text(i, "isgiftitem") == "1" for i in items):
        return False
    if _text(row, "redemptionlimit") not in (None, "0"):
        return False
    if max_qty is not None and max_qty < min_qty:
        return False
    if len(barcodes) > 1:
        item_prices = {_text(i, "discountedprice") for i in items} - {None}
        if _group_count(row) > 1 or len(item_prices) > 1 or not price_is_total:
            return False
    return True
```

In `normalize_promotion` compute `price_is_total = _price_is_total(description, min_qty, price)` once before the `return PromoRecord(...)`, pass it to `_basket_eligible(row, items, rewards, barcodes, min_qty, price, max_qty, price_is_total)` and set `price_is_total=price_is_total` in the record.

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_promo_loader.py tests/test_parse_chain.py -v`
Expected: all PASS (B1's single-product tests unchanged).

- [ ] **Step 5: Commit**

```bash
git switch -c promotions-phase-b2 promotions-phase-b1
git add app/parser/promo_loader.py tests/test_promo_loader.py
git commit -m "Basket promotions: group promotions with a confirmed price are basket eligible"
```

---

### Task 2: The pricing engine (`price_store`)

**Files:**
- Modify: `app/basket_promos.py`
- Test: `tests/test_basket_promos.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class StorePromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal               # total for min_qty units
    max_qty: Optional[int]       # most units one purchase gets at the promotion price (all products together)
    price_is_total: bool
    product_ids: frozenset[int]  # the promotion's products that are in the basket and sold in this store

@dataclass(frozen=True)
class AppliedPromo:
    promo: StorePromo
    sets: int
    units: dict[int, int]        # product_id -> units covered
    saving: Decimal              # shelf price of the covered units minus sets * price

def price_store(lines: Mapping[int, tuple[Decimal, int]], promos: Sequence[StorePromo]) -> list[AppliedPromo]
```

`lines` maps `product_id -> (shelf unit price, quantity)`. `price_line` (B1) keeps its signature and result and becomes a wrapper.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_basket_promos.py`)

```python
# ── price_store: group promotions pooled across products (Phase B2) ──────────

from app.basket_promos import StorePromo, price_store


def sp(pid="g", n=3, price="10.00", cap=None, total=True, products=(1, 2), desc="3 ב-10"):
    return StorePromo(pid, desc, n, D(price), cap, total, frozenset(products))


def test_a_group_promotion_pools_the_quantities_of_its_products():
    lines = {1: (D("4.00"), 2), 2: (D("5.00"), 1)}          # 3 units: 4 + 4 + 5
    [applied] = price_store(lines, [sp()])
    assert applied.sets == 1 and applied.saving == D("3.00") and applied.units == {1: 2, 2: 1}


def test_the_cheapest_units_are_taken_first_so_a_saving_is_never_overstated():
    lines = {1: (D("2.00"), 1), 2: (D("9.00"), 2)}          # units 2, 9, 9; a set of 2 takes the 2 and a 9
    [applied] = price_store(lines, [sp(n=2, price="10.00")])
    assert applied.saving == D("1.00") and applied.units == {1: 1, 2: 1}


def test_fewer_units_than_the_set_size_means_no_promotion():
    assert price_store({1: (D("4.00"), 1), 2: (D("5.00"), 1)}, [sp(n=3)]) == []


def test_units_left_over_after_full_sets_stay_at_shelf_price():
    lines = {1: (D("4.00"), 2), 2: (D("5.00"), 3)}          # 5 units, one set of 3
    [applied] = price_store(lines, [sp()])
    assert applied.sets == 1 and sum(applied.units.values()) == 3


def test_several_full_sets():
    lines = {1: (D("4.00"), 3), 2: (D("5.00"), 3)}          # sets [4,4,4] and [5,5,5]
    [applied] = price_store(lines, [sp()])
    assert applied.sets == 2 and applied.saving == D("7.00")


def test_a_purchase_limit_caps_the_units_covered_across_the_group():
    [applied] = price_store({1: (D("4.00"), 4), 2: (D("5.00"), 4)}, [sp(cap=3)])
    assert applied.sets == 1


def test_a_one_unit_group_price_only_applies_to_units_dearer_than_the_price():
    lines = {1: (D("12.00"), 2), 2: (D("8.00"), 1)}
    [applied] = price_store(lines, [sp(n=1, price="10.00", desc="1 ב-10")])
    assert applied.units == {1: 2} and applied.saving == D("4.00")      # the 8.00 unit is cheaper than the price


def test_an_unconfirmed_price_at_or_below_one_unit_is_not_trusted():
    lines = {1: (D("9.90"), 2)}
    assert price_store(lines, [sp(n=2, price="7.90", total=False, products=(1,))]) == []
    assert len(price_store(lines, [sp(n=2, price="7.90", total=True, products=(1,))])) == 1


def test_nonsense_promotions_are_ignored():
    lines = {1: (D("4.00"), 3)}
    assert price_store(lines, [sp(price="0.00", products=(1,)), sp(n=0, products=(1,))]) == []


def test_a_product_is_covered_by_one_promotion_only():
    lines = {1: (D("4.00"), 4)}
    twos = sp("a", n=2, price="6.00", products=(1,), desc="2 ב-6")        # saving 2 per set, 4 in total
    fours = sp("b", n=4, price="10.00", products=(1,), desc="4 ב-10")     # saving 6
    [applied] = price_store(lines, [twos, fours])
    assert applied.promo.promotion_id == "b"


def test_the_largest_saving_wins_a_shared_product():
    lines = {1: (D("4.00"), 2), 2: (D("5.00"), 2)}
    single = sp("a", n=2, price="6.00", products=(1,), desc="2 ב-6")      # saves 2
    pooled = sp("g", n=3, price="10.00", products=(1, 2))                # [4,4,5] saves 3
    [applied] = price_store(lines, [single, pooled])
    assert applied.promo.promotion_id == "g"


def test_a_promotion_on_other_products_still_applies_next_to_a_group():
    lines = {1: (D("4.00"), 3), 2: (D("5.00"), 1), 3: (D("7.00"), 2)}
    group_promo = sp("g", n=3, price="10.00", products=(1, 2))           # [4,4,4] saves 2
    other = sp("o", n=2, price="12.00", products=(3,), desc="2 ב-12")     # saves 2
    assert {a.promo.promotion_id for a in price_store(lines, [group_promo, other])} == {"g", "o"}


def test_a_tie_is_decided_by_promotion_id():
    lines = {1: (D("4.00"), 3)}
    first, second = sp("a", products=(1,)), sp("b", products=(1,))
    assert price_store(lines, [second, first])[0].promo.promotion_id == "a"
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_basket_promos.py -v -k "price_store or group or pooled"`
Expected: FAIL at import: `ImportError: cannot import name 'StorePromo'`.

- [ ] **Step 3: Implement** (replace the body of `app/basket_promos.py`; keep `BasketPromo` and `PricedLine` exactly as they are, add the rest, and turn `price_line` into a wrapper)

```python
# app/basket_promos.py
#
# Price a store's basket lines with its "N for X" promotions (Phase B1 single products, B2 groups).
#
# Deliberately conservative, so a promotion can only ever make a total cheaper than the shelf price by an
# amount the shopper can really get:
#  - a product is covered by at most one promotion (promotions are not mixed on a product)
#  - among promotions the one with the largest total saving goes first; ties go to the lowest promotion_id
#  - the units of a group promotion are taken cheapest first, so the saving is the smallest possible
#  - a set that saves nothing is never taken, and a purchase limit (max_qty) caps the units covered
#  - an N>1 price at or below the cheapest unit's shelf price is trusted only when the promotion's own
#    text confirmed it as the total for N (otherwise it may be a per-unit price)

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Sequence


@dataclass(frozen=True)
class BasketPromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal
    max_qty: Optional[int]
    price_is_total: bool = False


@dataclass(frozen=True)
class PricedLine:
    total: Decimal
    regular_total: Decimal
    promo: Optional[BasketPromo] = None
    sets: int = 0


@dataclass(frozen=True)
class StorePromo:
    promotion_id: str
    description: str
    min_qty: int
    price: Decimal
    max_qty: Optional[int]
    price_is_total: bool
    product_ids: frozenset[int]


@dataclass(frozen=True)
class AppliedPromo:
    promo: StorePromo
    sets: int
    units: dict[int, int]
    saving: Decimal


def _evaluate(promo: StorePromo, lines: Mapping[int, tuple[Decimal, int]], locked: set[int]) -> Optional[AppliedPromo]:
    """The most this promotion can save on the basket's still-free products, or None."""
    if promo.min_qty < 1 or promo.price <= 0:
        return None
    pool = sorted(
        (lines[pid][0], pid)
        for pid in promo.product_ids
        if pid in lines and pid not in locked
        for _ in range(lines[pid][1])
    )
    if not pool:
        return None
    if promo.min_qty > 1 and promo.price <= pool[0][0] and not promo.price_is_total:
        return None                       # "N for no more than one unit": maybe a per-unit price, do not trust
    if promo.max_qty is not None:
        pool = pool[:promo.max_qty]       # the cap covers the cheapest units: the smallest saving
    n = promo.min_qty
    covered: dict[int, int] = {}
    saving = Decimal("0")
    sets = 0
    for start in range(0, len(pool) - n + 1, n):
        window = pool[start:start + n]
        gain = sum((price for price, _ in window), Decimal("0")) - promo.price
        if gain <= 0:
            continue                      # a set that saves nothing stays at shelf price
        saving += gain
        sets += 1
        for _, pid in window:
            covered[pid] = covered.get(pid, 0) + 1
    return AppliedPromo(promo, sets, covered, saving) if sets else None


def price_store(lines: Mapping[int, tuple[Decimal, int]], promos: Sequence[StorePromo]) -> list[AppliedPromo]:
    """Which promotions apply to a store's basket, and what each saves. `lines`: product_id -> (shelf price, quantity)."""
    locked: set[int] = set()
    remaining = sorted(promos, key=lambda p: p.promotion_id)
    applied: list[AppliedPromo] = []
    while remaining:
        best: Optional[AppliedPromo] = None
        for promo in remaining:
            candidate = _evaluate(promo, lines, locked)
            if candidate is not None and (best is None or candidate.saving > best.saving):
                best = candidate
        if best is None:
            break
        applied.append(best)
        locked |= set(best.units)
        remaining = [p for p in remaining if p is not best.promo]
    return applied


def price_line(unit_price: Decimal, quantity: int, promos: Sequence[BasketPromo]) -> PricedLine:
    """One product at one store (Phase B1): the single-product case of price_store."""
    regular = unit_price * quantity
    wrapped = [
        StorePromo(p.promotion_id, p.description, p.min_qty, p.price, p.max_qty, p.price_is_total, frozenset({0}))
        for p in promos
    ]
    applied = price_store({0: (unit_price, quantity)}, wrapped)
    if not applied:
        return PricedLine(total=regular, regular_total=regular)
    best = applied[0]
    original = next(p for p, w in zip(promos, wrapped) if w is best.promo)
    return PricedLine(total=regular - best.saving, regular_total=regular, promo=original, sets=best.sets)
```

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_basket_promos.py -v`
Expected: all PASS — the 14 B1 `price_line` tests (now guarding the engine through the wrapper) plus the new ones. If a B1 `price_line` test fails, the engine changed single-product behaviour: fix the engine, not the test.

- [ ] **Step 5: Commit**

```bash
git add app/basket_promos.py tests/test_basket_promos.py
git commit -m "Basket promotions: price_store prices single-product and group promotions with one engine"
```

---

### Task 3: `/basket/compare` uses the engine and reports group promotions

**Files:**
- Modify: `app/api/schemas.py` (`BasketStoreTotal`), `app/api/routes.py` (`_basket_promotions`, `basket_compare`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `StorePromo`, `price_store` (Task 2); `basket_eligible` group rows (Task 1).
- Produces: `BasketStoreTotal.promo_adjustments: list[dict]`, each `{"description", "min_qty", "price", "sets", "saving", "barcodes"}`; `total_price = Σ line_total − Σ adjustment saving`; `savings` includes the adjustments; single-product promotions keep B1's per-line representation.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_api.py`)

```python
async def _group_world(session, *, with_group=True, group_age_days=0):
    """Store A is cheaper on the shelf; store B runs '3 for 10' on any of milk, yogurt and cheese."""
    from datetime import datetime, timedelta
    from sqlalchemy import func, update
    from zoneinfo import ZoneInfo
    from app.db.models import Chain, Price, Product, Promotion, Store

    chain_a, chain_b = Chain(chain_id="1", name="רשת א"), Chain(chain_id="2", name="רשת ב")
    session.add_all([chain_a, chain_b])
    await session.flush()
    store_a = Store(chain_id=chain_a.id, store_id="1", name="סניף א")
    store_b = Store(chain_id=chain_b.id, store_id="1", name="סניף ב")
    products = [Product(barcode=f"729000000030{i}", name=name) for i, name in enumerate(("חלב", "יוגורט", "גבינה"), 1)]
    session.add_all([store_a, store_b, *products])
    await session.flush()
    now = datetime(2026, 10, 12)
    shelf_a, shelf_b = ("4.00", "5.00", "6.00"), ("5.00", "6.00", "7.00")
    for product, a, b in zip(products, shelf_a, shelf_b):
        session.add_all([
            Price(product_id=product.id, store_id=store_a.id, price=a, price_updated_at=now, is_current=True),
            Price(product_id=product.id, store_id=store_b.id, price=b, price_updated_at=now, is_current=True),
        ])
    local_now = datetime.now(ZoneInfo("Asia/Jerusalem")).replace(tzinfo=None)
    if with_group:
        for product in products:
            session.add(Promotion(
                product_id=product.id, store_id=store_b.id, promotion_id="g1", description="3 מוצרי חלב ב-10",
                min_qty=3, discounted_price="10.00", basket_eligible=True, price_is_total=True, is_active=True,
                start_date=local_now - timedelta(days=5), end_date=local_now + timedelta(days=5)))
    await session.commit()
    await session.execute(update(Store).where(Store.id == store_b.id).values(
        last_promo_at=func.now() - timedelta(days=group_age_days)))
    await session.commit()
    return products


async def _group_basket(client, quantities):
    body = [{"barcode": f"729000000030{i}", "quantity": q} for i, q in enumerate(quantities, 1) if q]
    r = await client.post("/api/v1/basket/compare", json=body)
    assert r.status_code == 200
    return r.json()


async def test_a_group_promotion_pools_different_products_and_can_flip_the_ranking(client, session):
    await _group_world(session)
    body = await _group_basket(client, (1, 1, 1))           # A: 4+5+6 = 15.00, B: shelf 18.00, promotion 10.00
    assert [s["store"]["chain"]["name"] for s in body["stores"]] == ["רשת ב", "רשת א"]
    b = _by_chain(body)["רשת ב"]
    assert (float(b["total_price"]), float(b["savings"]), b["promotions_known"]) == (10.0, 8.0, True)
    [adjustment] = b["promo_adjustments"]
    assert adjustment["description"] == "3 מוצרי חלב ב-10" and adjustment["sets"] == 1
    assert float(adjustment["saving"]) == 8.0 and sorted(adjustment["barcodes"]) == ["7290000000301", "7290000000302", "7290000000303"]
    assert all(line["promo"] is None for line in b["item_prices"])         # group savings are not spread over lines
    assert sum(float(line["line_total"]) for line in b["item_prices"]) == 18.0


async def test_the_basket_below_the_set_size_gets_no_group_promotion(client, session):
    await _group_world(session)
    body = await _group_basket(client, (1, 1, 0))
    b = _by_chain(body)["רשת ב"]
    assert float(b["total_price"]) == 11.0 and b["promo_adjustments"] == []


async def test_a_store_without_fresh_promotion_data_gets_no_group_promotion(client, session):
    await _group_world(session, group_age_days=8)
    b = _by_chain(await _group_basket(client, (1, 1, 1)))["רשת ב"]
    assert (float(b["total_price"]), b["promo_adjustments"], b["promotions_known"]) == (18.0, [], False)


async def test_stores_without_any_promotion_report_an_empty_adjustment_list(client, session):
    await _group_world(session, with_group=False)
    for store in (await _group_basket(client, (1, 1, 1)))["stores"]:
        assert store["promo_adjustments"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `venv/bin/python -m pytest tests/test_api.py -v -k "group"`
Expected: FAIL with `KeyError: 'promo_adjustments'`.

- [ ] **Step 3: Implement.**

`app/api/schemas.py`, in `BasketStoreTotal` after `promotions_known`:

```python
    # Promotions that cover several products at once: each is subtracted from the total as a whole
    # ({description, min_qty, price, sets, saving, barcodes}); single-product promotions are on their lines.
    promo_adjustments: List[dict] = []
```

`app/api/routes.py`: change the import to `from app.basket_promos import StorePromo, price_store` and replace `_basket_promotions` with:

```python
async def _basket_promotions(db: AsyncSession, product_ids: list[int], store_ids: list[int]) -> dict[int, list[StorePromo]]:
    """Promotions safe to price a basket with, running now, per store: each with the basket products it covers there."""
    if not product_ids or not store_ids:
        return {}
    rows = await db.execute(
        select(
            Promotion.store_id, Promotion.product_id, Promotion.promotion_id, Promotion.description,
            Promotion.min_qty, Promotion.discounted_price, Promotion.max_qty, Promotion.price_is_total,
        ).where(
            Promotion.product_id.in_(product_ids),
            Promotion.store_id.in_(store_ids),
            Promotion.basket_eligible,
            Promotion.min_qty.is_not(None),
            Promotion.discounted_price.is_not(None),
            _running_now(),
        )
    )
    heads: dict[tuple[int, str], tuple] = {}
    members: dict[tuple[int, str], set[int]] = {}
    for store_id, product_id, promotion_id, description, min_qty, price, max_qty, price_is_total in rows.all():
        key = (store_id, promotion_id)
        heads.setdefault(key, (description or "", min_qty, price, max_qty, price_is_total))
        members.setdefault(key, set()).add(product_id)
    by_store: dict[int, list[StorePromo]] = {}
    for (store_id, promotion_id), (description, min_qty, price, max_qty, price_is_total) in heads.items():
        by_store.setdefault(store_id, []).append(
            StorePromo(promotion_id, description, min_qty, price, max_qty, price_is_total,
                       frozenset(members[(store_id, promotion_id)])))
    return by_store
```

In `basket_compare`: delete the line `promos_by_line = await _basket_promotions(db, list(by_id)) if by_id else {}`, then replace everything from `# Step 4` down to (and including) the `ranked.sort(...)` line and the Step 6 block with the following (re-read the function first: the `ranked` tuples are unpacked in several places and all of them change to the 6-tuple `(missing, total, savings, adjustments, r, items)`):

```python
    # Step 4: Group prices by store: store_pk -> (row, {barcode -> item})
    grouped: dict = {}
    for r in all_price_rows:
        product = by_id[r.product_id]
        qty = quantity_map.get(product.barcode, 1)
        entry = grouped.get(r.store_pk)
        if entry is None:
            entry = grouped[r.store_pk] = (r, {})
        entry[1][product.barcode] = {
            "product_name": product.name,
            "barcode": product.barcode,
            "unit_price": r.price,
            "quantity": qty,
            "line_total": r.price * qty,
            "regular_line_total": r.price * qty,
            "promo": None,
        }

    # Step 4b: Promotions, only for stores whose promotion data is fresh. A promotion on one basket product
    # goes on its line (as in B1); one that covers several basket products is a store-level adjustment.
    fresh_stores = [store_pk for store_pk, (r, _) in grouped.items() if r.promo_known]
    promos_by_store = await _basket_promotions(db, list(by_id), fresh_stores)
    id_of = {p.barcode: p.id for p in by_id.values()}
    barcode_of = {pid: barcode for barcode, pid in id_of.items()}
    adjustments_by_store: dict[int, list[dict]] = {}
    for store_pk, promos in promos_by_store.items():
        items_by_barcode = grouped[store_pk][1]
        lines = {id_of[b]: (info["unit_price"], info["quantity"]) for b, info in items_by_barcode.items()}
        for applied in price_store(lines, promos):
            promo = applied.promo
            if len(applied.units) == 1:
                (pid,) = applied.units
                info = items_by_barcode[barcode_of[pid]]
                info["line_total"] = info["regular_line_total"] - applied.saving
                info["promo"] = {"description": promo.description, "min_qty": promo.min_qty,
                                 "price": promo.price, "sets": applied.sets}
            else:
                adjustments_by_store.setdefault(store_pk, []).append({
                    "description": promo.description, "min_qty": promo.min_qty, "price": promo.price,
                    "sets": applied.sets, "saving": applied.saving,
                    "barcodes": [barcode_of[pid] for pid in applied.units],
                })

    # Step 5: Total per store (of the items it has), then sort: complete baskets first, cheapest first
    ranked = []
    for store_pk, (r, items_by_barcode) in grouped.items():
        adjustments = adjustments_by_store.get(store_pk, [])
        adjusted = sum((a["saving"] for a in adjustments), Decimal("0"))
        total = sum((info["line_total"] for info in items_by_barcode.values()), Decimal("0")) - adjusted
        savings = sum((info["regular_line_total"] - info["line_total"] for info in items_by_barcode.values()), Decimal("0")) + adjusted
        ranked.append((len(barcodes) - len(items_by_barcode), total, savings, adjustments, r, items_by_barcode))
    ranked.sort(key=lambda x: (x[0], x[1]))

    complete_totals = [t for missing, t, _, _, _, _ in ranked if missing == 0]
    if len(complete_totals) >= 2:
        max_savings = complete_totals[-1] - complete_totals[0]
        max_total = complete_totals[-1]
    else:
        max_savings = Decimal("0")
        max_total = max((t for _, t, _, _, _, _ in ranked), default=Decimal("0"))
    cheapest_store = ranked[0][4].store_name if ranked else None
```

and in Step 6 change the comprehension header to `for missing, total, savings, adjustments, r, items_by_barcode in shown` and add `promo_adjustments=adjustments,` after `promotions_known=bool(r.promo_known),`. Remove the now unused `price_line`/`BasketPromo` import if nothing else uses it.

- [ ] **Step 4: Run to verify they pass**

Run: `venv/bin/python -m pytest tests/test_api.py -v`
Expected: all PASS — the four new tests and every B1 basket test (single-product behaviour unchanged).

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas.py app/api/routes.py tests/test_api.py
git commit -m "Basket promotions: price group promotions in the basket and report them as adjustments"
```

---

### Task 4: Show group promotions on the basket page

**Files:**
- Modify: `frontend/src/types.ts`, `frontend/src/pages/BasketPage.tsx`, `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: `promo_adjustments` (Task 3).
- Produces: `PromoAdjustment` type; `BasketStoreTotal.promo_adjustments?`.

No frontend test runner: verification is `tsc`, a build and the browser check in Step 4.

- [ ] **Step 1: Types** (`frontend/src/types.ts`). Above `BasketStoreTotal` add:

```ts
export interface PromoAdjustment {
  description: string;
  min_qty: number;
  price: number | string;
  sets: number;
  saving: number | string;
  barcodes: string[];
}
```

and add `promo_adjustments?: PromoAdjustment[];` to `BasketStoreTotal`.

- [ ] **Step 2: Result card** (`BasketPage.tsx`, `ResultCard`). Under the item name, after the existing `item.promo` block, add:

```tsx
              {!item.promo && (store.promo_adjustments ?? []).some(a => a.barcodes.includes(item.barcode)) && (
                <div className="basket-breakdown-promo">במבצע משותף</div>
              )}
```

and before the existing "הסכום כולל מבצעים" saving row add:

```tsx
        {(store.promo_adjustments ?? []).map((a, i) => (
          <div key={`adj-${i}`} className="basket-breakdown-row basket-breakdown-adjustment">
            <div className="basket-breakdown-name" title={a.description}>
              <div className="basket-breakdown-promo">מבצע: {a.description}{a.sets > 1 ? ` (×${a.sets})` : ''}</div>
            </div>
            <span className="basket-breakdown-line tabular">−{fmt(a.saving)}</span>
          </div>
        ))}
```

Extend the page note condition/text so it also mentions groups: change the sentence in the `basket-promo-note` to: `הסכומים כוללים מבצעי "N ב-X" (על מוצר בודד או על קבוצת מוצרים), בסניפים שיש לנו עבורם נתוני מבצעים. מבצעי מועדון וקופונים לא נכללים.`

- [ ] **Step 3: CSS.** Append to `global.css`:

```css
/* Basket group promotions: the saving row of a promotion that covers several items */
.basket-breakdown-adjustment { background: var(--orange-50); }
```

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit && npx vite build`
Expected: no errors. Then with the Task 5 demo database: at 375 px add three different products of one demo group promotion to the basket, open `/#/basket`, compare; expect the "מבצע: … (×n)" row with a negative amount, "במבצע משותף" under the covered items, the total equal to the shelf total minus the adjustment, no horizontal overflow, and an unchanged card for a store without promotions. Reset the viewport, stop the preview and remove the temporary `.claude/launch.json` entry afterwards.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types.ts frontend/src/pages/BasketPage.tsx frontend/src/styles/global.css
git commit -m "Basket promotions: show group promotions as a saving row in the store card"
```

---

### Task 5: Real-data demo, docs, rollout

**Files:**
- Modify: `CLAUDE.md`, `docs/deployment.md`

- [ ] **Step 1: Demo database with real files.** Same recipe as B1, never against the user's dev database:

```bash
S=<scratchpad>; mkdir -p $S/demo/dumps/Shufersal
cp dumps/Shufersal/PriceFull7290027600007-742-202602190300.xml dumps/Shufersal/PromoFull7290027600007-742-202602190300.xml dumps/Shufersal/Stores7290027600007-000-202605120201.xml $S/demo/dumps/Shufersal/
export DATABASE_URL=<.env URL with database name sm_promo_demo> DUMPS_DIR=$S/demo/dumps SCRAPE_PROMOS=true PROMO_CHAINS=SHUFERSAL DELETE_AFTER_INGEST=false
# create the empty database sm_promo_demo, then:
venv/bin/python -m alembic upgrade head
venv/bin/python -m app.parser.mass_parser SHUFERSAL
```

Find a running-or-movable group promotion: `SELECT promotion_id, description, min_qty, discounted_price, count(*) FROM promotions WHERE basket_eligible GROUP BY 1,2,3,4 HAVING count(*) > 1 ORDER BY 5 DESC LIMIT 10;` (the file is from February, so move one promotion's `end_date` into the future *in the throwaway database only*). Give store 742 a name and city (the page hides unnamed stores), add a second store in another chain with the same products at a slightly lower shelf price and no promotion data, start the API on port 8011 with `FRONTEND_URL=http://localhost:3011` and a temporary `frontend-demo` entry in the git-ignored `.claude/launch.json` (`env VITE_API_URL=http://localhost:8011 PORT=3011 npm run dev --prefix frontend`). The app uses a hash router: `http://localhost:3011/#/basket`. Drop the database afterwards.

- [ ] **Step 2: Document.** In `CLAUDE.md`, in the `/basket/compare` bullet add: "A promotion that covers several basket products is returned as a store-level entry in `promo_adjustments` and subtracted from `total_price`". Replace the Phase B1 rule paragraph (`A promotion changes a basket total only when it is basket_eligible`) with:

```
**A promotion changes a basket total only when it is `basket_eligible`.** One product, or a group of products whose price the promotion text confirms ("N ב-price"); reward 1 or 10; one `<Group>`; not weighted/gift/redemption-limited; running now; the store's promotion data fresh (`stores.last_promo_at`, 7 days). `app/basket_promos.price_store` applies them: a product belongs to at most one promotion, the largest total saving goes first, a group's sets take the cheapest units first, a set that saves nothing is never taken. Club, coupon, reward-3 and multi-`<Group>` promotions stay display-only.
```

In `docs/deployment.md` (Promotions section) add: group promotions become basket-eligible as each store's next promotion file loads, so the first cycle after the deploy fills them; check `select count(*) filter (where basket_eligible), count(distinct promotion_id) filter (where basket_eligible) from promotions;`; and a sanity query for the biggest group discounts:

```sql
select pr.store_id, pr.promotion_id, pr.description, pr.min_qty, pr.discounted_price, count(*) as products
  from promotions pr
 where pr.basket_eligible
 group by 1, 2, 3, 4, 5
having count(*) > 1
 order by products desc
 limit 30;
```

- [ ] **Step 3: Full test run**

Run: `venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md docs/deployment.md
git commit -m "Basket promotions: document group promotions, the engine rules and the rollout checks"
```

---

## Rollout (after merge, owned by the user)

1. Merge in order: Phase A, B1, B2 (each builds on the previous one). B2 needs no migration.
2. Group promotions become `basket_eligible` only as each store's next promotion file loads (the first cycle after the deploy).
3. After the first cycle, run the sanity queries from `docs/deployment.md` and compare a few big group promotions' texts with their stored price before more chains are switched on.
4. The cheapest-units-first allocation is the safe reading (it can only overstate a total, never understate it). If chains' registers are known to apply a group promotion to the most expensive units, the saving shown is a lower bound.

## Self-Review

- **Coverage:** eligibility incl. confirmation, multi-group, differing prices, N=1 (T1); pooling, cheapest-first, remainder, several sets, cap, N=1, unconfirmed per-unit guard, one-promotion-per-product, largest saving first, disjoint promotions, ties (T2); API incl. ranking flip, below set size, stale store, empty list, and B1 behaviour via the unchanged B1 tests (T3); UI (T4); demo/docs/rollout (T5). Review Focus 1→T2 (cheapest-first, locks, non-positive sets); 2→T2 + T3; 3→T1; 4→T2; 5→T3 (store-restricted query, engine only for stores with promotions).
- **Placeholders:** none; the only angle-bracket values are environment paths in the manual demo commands of T5 Step 1.
- **Names:** `StorePromo`, `AppliedPromo`, `price_store`, `price_line`, `_basket_promotions(db, product_ids, store_ids)`, `promo_adjustments`, `price_is_total`, `_group_count`, `_FOR_X`, `_N_FOR_X` are used identically across tasks.
- **Known unknowns the executor must check, not assume:** (a) T3 changes the `ranked` tuple to 6 elements: re-read `basket_compare` and update every unpack site (complete_totals, max_total, cheapest_store `ranked[0][4]`, Step 6); (b) the replaced B1 test `test_two_products_are_never_eligible` is intentionally superseded; (c) "any N of the group" and cheapest-first were not checked against a till; (d) the engine runs once per store that has promotions: measure the 100-item basket over the demo/real data before enabling more chains if response time matters.
