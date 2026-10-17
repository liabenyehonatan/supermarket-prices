# app/chains.py
#
# One chain feed can hold several brands. The "Yaynot Bitan and Carrefour" feed lists the
# Yeinot Bitan stores and the (much more numerous) Carrefour ones together under one chain id,
# so users saw the Bitan logo on Carrefour branches. The brand is told apart by the store name.

from sqlalchemy import case

from app.db.models import Chain, Store

# Publishers that are not supermarkets (scraper names). Never scraped and never parsed, whatever SKIP_CHAINS says.
# H. Cohen is a wholesaler (decided 2026-10-17); its data was removed with app/pipeline/remove_chain.py.
NOT_SUPERMARKETS = {"HET_COHEN", "HET_COHEN_NEW_SOURCE"}

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
