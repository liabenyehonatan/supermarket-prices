"""remove_chain: a dry run changes nothing; applying removes one chain and what only it sold, and nothing else."""

from datetime import datetime

from sqlalchemy import func, select

from app.db.models import Chain, IngestedFile, Price, Product, Promotion, Store
from app.pipeline.remove_chain import remove_chain


async def _fixture(session):
    cohen = Chain(chain_id="7290000000111", name="ח. כהן")
    shufersal = Chain(chain_id="7290027600007", name="שופרסל")
    session.add_all([cohen, shufersal])
    await session.flush()
    c1 = Store(chain_id=cohen.id, store_id="1", name="כהן סניף")
    s1 = Store(chain_id=shufersal.id, store_id="1", name="שופרסל דיל")
    shared = Product(barcode="7290000000301", name="מוצר משותף")
    only_cohen = Product(barcode="7290000000302", name="מוצר של כהן בלבד")
    only_shufersal = Product(barcode="7290000000303", name="מוצר של שופרסל בלבד")
    session.add_all([c1, s1, shared, only_cohen, only_shufersal])
    await session.flush()
    now = datetime(2026, 10, 17)
    price = lambda prod, store, p: Price(product_id=prod.id, store_id=store.id, price=p, price_updated_at=now, is_current=True)
    session.add_all([
        price(shared, c1, "5.00"), price(shared, s1, "6.00"),
        price(only_cohen, c1, "9.00"), price(only_shufersal, s1, "4.00"),
        Promotion(product_id=only_cohen.id, store_id=c1.id, promotion_id="p1", description="x", is_active=True),
        Promotion(product_id=shared.id, store_id=s1.id, promotion_id="p2", description="y", is_active=True),
        IngestedFile(source_folder="HetCohen", file_name="PriceFull1.xml", file_type="price_full", status="done"),
        IngestedFile(source_folder="Shufersal", file_name="PriceFull2.xml", file_type="price_full", status="done"),
    ])
    await session.commit()


async def _count(session, model):
    return (await session.execute(select(func.count()).select_from(model))).scalar()


async def test_a_dry_run_counts_and_changes_nothing(session):
    await _fixture(session)
    counts = await remove_chain(session, "ח. כהן", ["HetCohen"], apply=False)
    assert counts == {"chains": 1, "stores": 1, "prices": 2, "promotions": 1, "orphan_products": 1, "ledger_rows": 1}
    assert await _count(session, Chain) == 2 and await _count(session, Price) == 4 and await _count(session, Product) == 3


async def test_applying_removes_only_that_chain_and_the_products_only_it_sold(session):
    await _fixture(session)
    await remove_chain(session, "ח. כהן", ["HetCohen"], apply=True)
    await session.commit()
    assert [c.name for c in (await session.execute(select(Chain))).scalars()] == ["שופרסל"]
    assert await _count(session, Store) == 1
    assert await _count(session, Price) == 2                                   # the shared product keeps Shufersal's price
    assert await _count(session, Promotion) == 1                               # Shufersal's promotion stays
    barcodes = {p.barcode for p in (await session.execute(select(Product))).scalars()}
    assert barcodes == {"7290000000301", "7290000000303"}                      # Cohen's own product is gone, the shared one stays
    folders = {f.source_folder for f in (await session.execute(select(IngestedFile))).scalars()}
    assert folders == {"Shufersal"}


async def test_an_unknown_name_removes_nothing(session):
    await _fixture(session)
    counts = await remove_chain(session, "לא קיים", [], apply=True)
    assert counts["chains"] == 0
    assert await _count(session, Chain) == 2


async def test_tens_of_thousands_of_products_only_one_chain_sold_are_removed_in_one_go(session):
    from sqlalchemy import insert

    cohen = Chain(chain_id="7290000000111", name="ח. כהן")
    session.add(cohen)
    await session.flush()
    store = Store(chain_id=cohen.id, store_id="1", name="כהן סניף")
    session.add(store)
    await session.flush()
    n = 40000                                                                   # more than the 32767 placeholders one statement may hold
    await session.execute(insert(Product), [{"barcode": f"729{i:010d}", "name": f"מוצר {i}"} for i in range(n)])
    ids = [r[0] for r in (await session.execute(select(Product.id))).all()]
    now = datetime(2026, 10, 17)
    await session.execute(insert(Price), [
        {"product_id": pid, "store_id": store.id, "price": "1.00", "price_updated_at": now, "is_current": True} for pid in ids
    ])
    await session.commit()
    counts = await remove_chain(session, "ח. כהן", [], apply=True)
    await session.commit()
    assert counts["orphan_products"] == n and counts["prices"] == n
    assert await _count(session, Product) == 0 and await _count(session, Price) == 0 and await _count(session, Chain) == 0
