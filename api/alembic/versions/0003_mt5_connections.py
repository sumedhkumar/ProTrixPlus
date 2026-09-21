"""mt5_connections table

Revision ID: 0003_mt5_connections
Revises: 0002_entitlements_and_catalog
Create Date: 2026-09-17

PRD 3.1/4.1/5.2: one connected MT5 account per client for MVP, with
connection-status validation. Never stores a password - see the model's
docstring in protrix_contracts/db/models.py.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0003_mt5_connections"
down_revision: str | None = "0002_entitlements_and_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if inspect(op.get_bind()).has_table("mt5_connections"):
        return
    op.create_table(
        "mt5_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("broker_server", sa.String(120), nullable=False),
        sa.Column("login", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", name="uq_mt5_connections_user_id"),
        sa.CheckConstraint(
            "status IN ('NOT_CONFIGURED', 'PENDING', 'CONNECTED', 'DISCONNECTED', 'ERROR')",
            name="status_allowed",
        ),
    )


def downgrade() -> None:
    op.drop_table("mt5_connections")
