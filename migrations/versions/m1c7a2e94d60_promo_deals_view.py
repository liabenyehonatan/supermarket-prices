"""promo_deals: one row per (brand, promotion), with the saving against the cheapest shelf price

Revision ID: m1c7a2e94d60
Revises: l9b6f2c18e53
Create Date: 2026-10-14 20:00:00

The promotions section reads this view; the worker refreshes it after each cycle (after product_store_counts,
which it joins for the market price). The brand rule is the SQL twin of app/chains.display_chain_name
(a test pins them together).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "m1c7a2e94d60"
down_revision: Union[str, None] = "l9b6f2c18e53"
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
   WHERE pr.basket_eligible AND pr.is_active
     AND pr.min_qty IS NOT NULL AND pr.discounted_price IS NOT NULL
     AND s.last_promo_at >= now() - interval '7 days'
     AND (s.name IS NULL OR s.name NOT ILIKE '%סיטונ%')
     AND (pr.start_date IS NULL OR pr.start_date <= (now() AT TIME ZONE 'Asia/Jerusalem'))
     AND (pr.end_date   IS NULL OR pr.end_date   >= (now() AT TIME ZONE 'Asia/Jerusalem'))
), deals AS (
  SELECT brand, promotion_id, description, min_qty, price, max_qty, price_is_total,
         min(end_date) AS ends_at,
         array_agg(DISTINCT store_id)   AS store_ids,
         array_agg(DISTINCT product_id) AS product_ids
    FROM running
   GROUP BY brand, promotion_id, description, min_qty, price, max_qty, price_is_total
), ref AS (
  SELECT d.brand, d.promotion_id, d.description, d.min_qty, d.price, d.max_qty, d.price_is_total,
         min(v.min_price) AS ref_price
    FROM deals d
    CROSS JOIN LATERAL unnest(d.product_ids) AS u(product_id)
    JOIN product_store_counts v ON v.product_id = u.product_id
   WHERE v.min_price >= 0.5
   GROUP BY d.brand, d.promotion_id, d.description, d.min_qty, d.price, d.max_qty, d.price_is_total
)
SELECT md5(d.brand || '|' || d.promotion_id || '|' || d.min_qty || '|' || d.price || '|' || d.description
           || '|' || coalesce(d.max_qty::text, '') || '|' || d.price_is_total::text) AS deal_id,
       d.brand, d.promotion_id, d.description, d.min_qty, d.price, d.max_qty, d.price_is_total, d.ends_at,
       d.store_ids, d.product_ids,
       cardinality(d.store_ids) AS stores, cardinality(d.product_ids) AS products,
       d.price / d.min_qty AS unit_price, r.ref_price,
       1 - (d.price / d.min_qty) / r.ref_price AS saving_pct
  FROM deals d
  JOIN ref r ON r.brand = d.brand AND r.promotion_id = d.promotion_id AND r.description = d.description
            AND r.min_qty = d.min_qty AND r.price = d.price AND r.price_is_total = d.price_is_total
            AND r.max_qty IS NOT DISTINCT FROM d.max_qty
"""


def upgrade() -> None:
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
    op.execute("DROP MATERIALIZED VIEW IF EXISTS promo_deals")
