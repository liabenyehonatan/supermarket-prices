# app/pipeline/remove_chain.py
"""
Remove one chain from the database: its stores, prices, promotions, the file-ledger rows of its dump folders, and the
products that only it sold. A one-off clean-up tool (for a publisher that turned out not to be a supermarket).

    python -m app.pipeline.remove_chain "ח. כהן" --folders HetCohen HetCohenNewSource            # dry run: counts only
    python -m app.pipeline.remove_chain "ח. כהן" --folders HetCohen HetCohenNewSource --apply    # deletes, one transaction

It does nothing without --apply. Everything is deleted in a single transaction, so a failure leaves the database as it
was; the two materialized views are refreshed afterwards. Take a pg_dump first. To stop the chain coming back, add its
scraper to NOT_SUPERMARKETS in app/scraper/mass_scraper.py.
"""

import argparse
import asyncio
import logging

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# More chain rows than this under one name means the name is wrong: refuse rather than delete a lot.
MAX_CHAIN_ROWS = 3


async def _count(session: AsyncSession, sql: str, **params) -> int:
    stmt = text(sql)
    for key, value in params.items():
        if isinstance(value, list):
            stmt = stmt.bindparams(bindparam(key, expanding=True))
    return int((await session.execute(stmt, params)).scalar() or 0)


async def remove_chain(session: AsyncSession, name: str, folders: list[str], apply: bool) -> dict[str, int]:
    """Count (and with apply=True delete) what belongs to the chain `name`. Returns the counts, before deleting."""
    rows = (await session.execute(text("SELECT id FROM chains WHERE name = :name"), {"name": name})).all()
    chain_ids = [r[0] for r in rows]
    if not chain_ids:
        return {"chains": 0, "stores": 0, "prices": 0, "promotions": 0, "orphan_products": 0, "ledger_rows": 0}
    if len(chain_ids) > MAX_CHAIN_ROWS:
        raise ValueError(f"{len(chain_ids)} chain rows are called {name!r}; refusing (limit {MAX_CHAIN_ROWS})")

    store_ids = [r[0] for r in (await session.execute(
        text("SELECT id FROM stores WHERE chain_id IN :c").bindparams(bindparam("c", expanding=True)), {"c": chain_ids})).all()]

    counts = {"chains": len(chain_ids), "stores": len(store_ids), "prices": 0, "promotions": 0, "orphan_products": 0}
    orphan_ids: list[int] = []
    if store_ids:
        counts["prices"] = await _count(session, "SELECT count(*) FROM prices WHERE store_id IN :s", s=store_ids)
        counts["promotions"] = await _count(session, "SELECT count(*) FROM promotions WHERE store_id IN :s", s=store_ids)
        # Products that were priced here and are priced or promoted nowhere else
        orphan_ids = [r[0] for r in (await session.execute(text("""
            SELECT p.id FROM products p
             WHERE p.id IN (SELECT product_id FROM prices WHERE store_id IN :s)
               AND NOT EXISTS (SELECT 1 FROM prices x WHERE x.product_id = p.id AND x.store_id NOT IN :s)
               AND NOT EXISTS (SELECT 1 FROM promotions x WHERE x.product_id = p.id AND x.store_id NOT IN :s)
        """).bindparams(bindparam("s", expanding=True)), {"s": store_ids})).all()]
        counts["orphan_products"] = len(orphan_ids)
    counts["ledger_rows"] = (
        await _count(session, "SELECT count(*) FROM ingested_files WHERE source_folder IN :f", f=folders) if folders else 0
    )

    if not apply:
        return counts

    async def run(sql: str, **params):
        stmt = text(sql)
        for key, value in params.items():
            if isinstance(value, list):
                stmt = stmt.bindparams(bindparam(key, expanding=True))
        await session.execute(stmt, params)

    if store_ids:
        await run("DELETE FROM promotions WHERE store_id IN :s", s=store_ids)
        await run("DELETE FROM prices WHERE store_id IN :s", s=store_ids)
    if orphan_ids:
        await run("DELETE FROM products WHERE id IN :p", p=orphan_ids)
    if store_ids:
        await run("DELETE FROM stores WHERE id IN :s", s=store_ids)
    await run("DELETE FROM chains WHERE id IN :c", c=chain_ids)
    if folders:
        await run("DELETE FROM ingested_files WHERE source_folder IN :f", f=folders)
    return counts


async def _main(name: str, folders: list[str], apply: bool) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            counts = await remove_chain(session, name, folders, apply)
    print(("DELETED" if apply else "DRY RUN (nothing deleted)") + f" for {name!r}: {counts}")
    if apply and counts["chains"]:
        from app.pipeline.maintenance import refresh_deals, refresh_popularity
        await refresh_popularity()
        await refresh_deals()
        print("Refreshed product_store_counts and promo_deals.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="the chain's name exactly as stored (chains.name)")
    parser.add_argument("--folders", nargs="*", default=[], help="its dump folders, to clear their file-ledger rows")
    parser.add_argument("--apply", action="store_true", help="really delete (without it: a dry run)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main(args.name, args.folders, args.apply))


if __name__ == "__main__":
    main()
