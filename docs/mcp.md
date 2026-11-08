# Claude connector (MCP)

A shopper can tell Claude what they need ("חלב 3%, ביצים L, לחם פרוס, שתי חבילות אורז"). Claude finds each product,
builds a basket, compares it across the chains, and answers with the cheapest branch, the total, the saving, a shopping
list to copy into a chain's own online shop, and a link that opens the finished basket on this site.

It is a separate, read-only service (`mcp_service/`, the `mcp` container). It has no database access: it asks the
`api` service over the docker network, so everything it says is what the site itself would say.

## Connect Claude to it

Claude (claude.ai, desktop or mobile) → Settings → Connectors → Add custom connector → URL `https://<your domain>/mcp`.
No sign-in is needed. In Claude Code: `claude mcp add --transport http sali https://<your domain>/mcp`.

## The tools

| Tool | What it does |
|---|---|
| `search_products` | Several searches in one call (up to 10 texts, 5 results each) with the cheapest price and unit price; sort by `relevance`, `cheapest` or `unit_price` |
| `get_product_prices` | The 5 cheapest offers for one product (chain, city, price, promotion, delivery link), optionally for one city or chain |
| `compare_basket` | Up to 40 products with quantities: the 3 cheapest branches with a complete basket, savings, missing items, a shopping list, and `open_in_site_url` |
| `get_products` | Names for a list of barcodes (for a pasted basket link) |
| `list_deals` | Current promotions, best first |
| `find_cities` | Spelling check for a city, before filtering by it |
| `list_chains` | The chains and how many branches each has |

Answers are deliberately short, and say how old the prices are (`prices_as_of`) and what is incomplete (`warnings`).

## The basket link

`https://<domain>/basket?items=<barcode>:<qty>,<barcode>:<qty>` — the site's basket page creates a **new** basket called
"מקלוד" with these products, makes it the active one, and removes the parameter from the address. Existing baskets are
never touched. Chains offer no public cart API, so filling a chain's own cart is not possible: the shopper copies the
shopping list instead.

## Limits (and where they live)

- 40 products per `compare_basket`; 10 searches per `search_products`; every API call has a 10 s timeout and at most 4
  run at once (`mcp_service/config.py`). The service reaches the API directly, past nginx, so it limits itself.
- nginx: `/mcp` has its own allowance, 2 requests/s per address with a burst of 10, and bodies up to 64 KB.
- Names and promotion text from the chains' sites are cut to 120 characters and treated as data, never instructions.

## Operating it

- `docker compose logs mcp`: one line per tool call (`tool=… ok=… duration_ms=… count=…`); never the shopper's words.
- `SITE_URL` (the same variable the api uses) sets the address in basket links and which `Host` the service accepts.
  Without it no links are returned.
- `deploy/deploy.sh` rebuilds `mcp` when `mcp_service/` changes and waits until `/mcp` lists its tools.
- Tests: `cd mcp_service && pip install -r requirements-dev.txt && python -m pytest -q` (no database needed).
