"""ingestion ledger, run log and price-table integrity

Revision ID: b7d41c9e5a20
Revises: 5532a7085020
Create Date: 2026-10-08 23:00:00

What this does
- ingested_files: ledger of parsed files (replaces "file exists on disk").
- ingest_runs: one row per worker cycle / chain / phase.
- prices: at most ONE current row per (store, product), enforced by a partial
  unique index. Any pre-existing duplicates are closed first, newest kept.
- prices: swap four generic indexes for two partial ones sized for the real
  queries; drop products.ix_products_barcode (duplicates the unique constraint).
- prices: lower fillfactor + autovacuum thresholds so the frequent
  is_current / scraped_at updates stay cheap (applies to newly written pages).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7d41c9e5a20"
down_revision: Union[str, None] = "5532a7085020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── new tables ────────────────────────────────────────────────────────────
    op.create_table(
        "ingested_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_folder", sa.String(length=100), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_applied", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_folder", "file_name", name="uq_ingested_files_source_name"),
    )
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("chain", sa.String(length=100), nullable=True),
        sa.Column("phase", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("files_ok", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rows_applied", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["ingest_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ingest_runs_started", "ingest_runs", ["started_at"])
    op.create_index(
        "ix_ingest_runs_phase_status", "ingest_runs", ["phase", "status", "finished_at"]
    )

    # ── one current price per (store, product) ────────────────────────────────
    # Close any existing duplicates (keep the row with the newest price date) so
    # the unique index below can be built on live data.
    op.execute(
        """
        UPDATE prices p
           SET is_current = false
          FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY store_id, product_id
                           ORDER BY price_updated_at DESC, id DESC
                       ) AS rn
                  FROM prices
                 WHERE is_current
               ) d
         WHERE p.id = d.id AND d.rn > 1
        """
    )
    op.create_index(
        "uq_prices_current_store_product",
        "prices",
        ["store_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_prices_current_product",
        "prices",
        ["product_id"],
        postgresql_include=["store_id", "price"],
        postgresql_where=sa.text("is_current"),
    )

    # ── drop indexes the two above replace ────────────────────────────────────
    op.drop_index("ix_prices_product_store", table_name="prices")
    op.drop_index("ix_prices_is_current", table_name="prices")
    op.drop_index("ix_prices_scraped_at", table_name="prices")
    op.drop_index("ix_products_barcode", table_name="products")

    # ── keep the hot table healthy ────────────────────────────────────────────
    op.execute(
        """
        ALTER TABLE prices SET (
            fillfactor = 90,
            autovacuum_vacuum_scale_factor = 0.02,
            autovacuum_analyze_scale_factor = 0.02
        )
        """
    )
    op.execute("ANALYZE prices")

    # Least-privilege API role (created by deploy/postgres/init/01-roles.sh).
    # Idempotent and a no-op where the role does not exist (local dev, tests).
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') THEN
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_ro;
            GRANT UPDATE (image_url) ON public.products TO api_ro;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE prices RESET (
            fillfactor, autovacuum_vacuum_scale_factor, autovacuum_analyze_scale_factor
        )
        """
    )
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=False)
    op.create_index("ix_prices_scraped_at", "prices", ["scraped_at"], unique=False)
    op.create_index("ix_prices_is_current", "prices", ["is_current"], unique=False)
    op.create_index("ix_prices_product_store", "prices", ["product_id", "store_id"], unique=False)

    op.drop_index("ix_prices_current_product", table_name="prices")
    op.drop_index("uq_prices_current_store_product", table_name="prices")

    op.drop_index("ix_ingest_runs_phase_status", table_name="ingest_runs")
    op.drop_index("ix_ingest_runs_started", table_name="ingest_runs")
    op.drop_table("ingest_runs")
    op.drop_table("ingested_files")
