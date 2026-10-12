# app/chains.py
#
# One chain feed can hold several brands. The "Yaynot Bitan and Carrefour" feed lists the
# Yeinot Bitan stores and the (much more numerous) Carrefour ones together under one chain id,
# so users saw the Bitan logo on Carrefour branches. The brand is told apart by the store name.

from sqlalchemy import case

from app.db.models import Chain, Store

MIXED_CHAIN = "יינות ביתן / קרפור"
BITAN = "יינות ביתן"
CARREFOUR = "קרפור"


def display_chain_name(chain_name: str, store_name: str | None) -> str:
    """The brand shown to users for a store of `chain_name`."""
    if chain_name == MIXED_CHAIN:
        return BITAN if BITAN.split()[1] in (store_name or "") else CARREFOUR
    return chain_name


def display_chain_name_sql():
    """The same rule as a SQL expression (needs Chain and Store in the query)."""
    return case(
        (Chain.name != MIXED_CHAIN, Chain.name),
        (Store.name.icontains(BITAN.split()[1], autoescape=True), BITAN),
        else_=CARREFOUR,
    )
