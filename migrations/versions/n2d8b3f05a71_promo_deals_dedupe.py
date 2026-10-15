"""promo_deals: one deal per brand, terms and products (chains file one promotion under several ids)

Revision ID: n2d8b3f05a71
Revises: m1c7a2e94d60
Create Date: 2026-10-15 10:00:00

m1c7a2e94d60 is already in production, so the view is rebuilt here, not edited there. The deal identity is now
(brand, min_qty, price, max_qty, price_is_total, products): 19% of the visible deals were copies of another deal.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "n2d8b3f05a71"
down_revision: Union[str, None] = "m1c7a2e94d60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_VIEW = """
CREATE MATERIALIZED VIEW promo_deals AS
WITH running AS (
  SELECT CASE WHEN c.name <> 'יינות ביתן / קרפור' THEN c.name
              WHEN s.name ILIKE '%ביתן%' THEN 'יינות ביתן'
              ELSE 'קרפור' END AS brand,
         pr.promotion_id, pr.description, pr.min_qty, pr.discounted_price AS price, pr.max_qty,
         pr.price_is_total, pr.end_date, pr.store_id, pr.product_id
    FROM promotions pr
    JOIN stores s ON s.id = pr.store_id
    JOIN chains c ON c.id = s.chain_id
    JOIN products p ON p.id = pr.product_id
   WHERE pr.basket_eligible AND pr.is_active
     AND pr.min_qty IS NOT NULL AND pr.discounted_price IS NOT NULL
     AND length(p.barcode) >= 7                       -- shorter codes are chain-internal: their prices mean nothing
     AND (pr.price_is_total OR pr.min_qty = 1)         -- an unconfirmed N-unit price may be a per-unit price
     AND s.last_promo_at >= now() - interval '7 days'
     AND (s.name IS NULL OR s.name NOT ILIKE '%סיטונ%')
     AND (pr.start_date IS NULL OR pr.start_date <= (now() AT TIME ZONE 'Asia/Jerusalem'))
     AND (pr.end_date   IS NULL OR pr.end_date   >= (now() AT TIME ZONE 'Asia/Jerusalem'))
), per_promotion AS (
  SELECT brand, promotion_id, description, min_qty, price, max_qty, price_is_total,
         min(end_date) AS ends_at,
         array_agg(DISTINCT store_id)   AS store_ids,
         array_agg(DISTINCT product_id) AS product_ids
    FROM running
   GROUP BY brand, promotion_id, description, min_qty, price, max_qty, price_is_total
), deals AS (
  -- chains file one promotion under several promotion_ids: the same terms on the same products is one deal
  SELECT md5(brand || '|' || min_qty || '|' || price || '|' || coalesce(max_qty::text, '') || '|'
             || price_is_total::text || '|' || product_ids::text) AS deal_id,
         brand, min(promotion_id) AS promotion_id,
         (array_agg(description ORDER BY length(description), description))[1] AS description,
         min_qty, price, max_qty, price_is_total, min(ends_at) AS ends_at,
         ARRAY(SELECT DISTINCT sid FROM per_promotion p2 CROSS JOIN LATERAL unnest(p2.store_ids) AS sid
                WHERE p2.brand = pp.brand AND p2.min_qty = pp.min_qty AND p2.price = pp.price
                  AND p2.max_qty IS NOT DISTINCT FROM pp.max_qty AND p2.price_is_total = pp.price_is_total
                  AND p2.product_ids = pp.product_ids ORDER BY sid) AS store_ids,
         product_ids
    FROM per_promotion pp
   GROUP BY brand, min_qty, price, max_qty, price_is_total, product_ids
), ref AS (
  SELECT d.deal_id,
         min(v.min_price) AS ref_price,
         -- every product is also sold by another brand: the reference is a real market price, not only the
         -- promoting brand's own shelf
         bool_and(EXISTS (
           SELECT 1 FROM prices p2
             JOIN stores s2 ON s2.id = p2.store_id
             JOIN chains c2 ON c2.id = s2.chain_id
            WHERE p2.product_id = u.product_id AND p2.is_current AND p2.price >= 0.5
              AND (CASE WHEN c2.name <> 'יינות ביתן / קרפור' THEN c2.name
                        WHEN s2.name ILIKE '%ביתן%' THEN 'יינות ביתן'
                        ELSE 'קרפור' END) <> d.brand)) AS vs_market
    FROM deals d
    CROSS JOIN LATERAL unnest(d.product_ids) AS u(product_id)
    JOIN product_store_counts v ON v.product_id = u.product_id
   WHERE v.min_price >= 0.5
   GROUP BY d.deal_id
)
SELECT d.deal_id,
       d.brand, d.promotion_id, d.description, d.min_qty, d.price, d.max_qty, d.price_is_total, d.ends_at,
       d.store_ids, d.product_ids,
       cardinality(d.store_ids) AS stores, cardinality(d.product_ids) AS products,
       d.price / d.min_qty AS unit_price, r.ref_price,
       1 - (d.price / d.min_qty) / r.ref_price AS saving_pct,
       r.vs_market
  FROM deals d
  JOIN ref r ON r.deal_id = d.deal_id
"""


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS promo_deals")
    op.execute(_VIEW)
    op.execute("CREATE UNIQUE INDEX ix_promo_deals_id ON promo_deals (deal_id)")
    op.execute("CREATE INDEX ix_promo_deals_saving ON promo_deals (saving_pct DESC)")
    op.execute("CREATE INDEX ix_promo_deals_brand ON promo_deals (brand)")
    op.execute("CREATE INDEX ix_promo_deals_stores ON promo_deals USING gin (store_ids)")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') THEN
            GRANT SELECT ON promo_deals TO api_ro;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    # back to the previous definition, read from the migration that created it
    import importlib.util
    from pathlib import Path

    path = Path(__file__).with_name("m1c7a2e94d60_promo_deals_view.py")
    spec = importlib.util.spec_from_file_location("m1c7a2e94d60", path)
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS promo_deals")
    previous.upgrade()
