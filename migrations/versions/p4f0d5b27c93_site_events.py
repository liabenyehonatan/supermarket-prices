"""site_events: the site's own visitor statistics (anonymous visits, clicks and actions)

The API's restricted role may add rows and read them, nothing else: a bug in the public API cannot rewrite the
statistics. Old rows are removed by the worker, which connects as the owner.

Revision ID: p4f0d5b27c93
Revises: o3e9c4a16b82
Create Date: 2026-11-04 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "p4f0d5b27c93"
down_revision: Union[str, None] = "o3e9c4a16b82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("visitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event", sa.String(24), nullable=False),
        sa.Column("path", sa.String(200), nullable=True),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("value", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(80), nullable=True),
        sa.Column("device", sa.String(10), nullable=False),
        sa.Column("os", sa.String(12), nullable=False),
        sa.Column("browser", sa.String(12), nullable=False),
    )
    op.create_index("ix_site_events_created_at", "site_events", ["created_at"])
    op.create_index("ix_site_events_visitor_created", "site_events", ["visitor_id", "created_at"])
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'api_ro') THEN
            GRANT SELECT, INSERT ON public.site_events TO api_ro;
            GRANT USAGE ON SEQUENCE public.site_events_id_seq TO api_ro;
          END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.drop_table("site_events")
