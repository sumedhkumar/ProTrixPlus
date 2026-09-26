"""users gains mt5_setup_fee_paid

Revision ID: 0011_mt5_setup_fee
Revises: 0010_merge_heads
Create Date: 2026-09-27

One-time, account-wide fee covering the real cost of provisioning a
user's MetaApi account - self_subscribe now requires this before a
client can request any strategy. Demo-only for now (no real payment
processor), same idempotent-migration style as prior additive columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0011_mt5_setup_fee"
down_revision: str | None = "0010_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    if not has_column("users", "mt5_setup_fee_paid"):
        op.add_column(
            "users",
            sa.Column("mt5_setup_fee_paid", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if has_column("users", "mt5_setup_fee_paid"):
        op.drop_column("users", "mt5_setup_fee_paid")
