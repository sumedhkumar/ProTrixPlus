"""entitlements, strategy catalog fields, execution P&L, password auth

Revision ID: 0002_entitlements_and_catalog
Revises: 0001_initial_skeleton
Create Date: 2026-09-17

Adds the columns needed for real entitlement gating (PRD 5.3/5.5/5.8) and
trade P&L attribution (PRD 5.6), and a password_hash for real client login
(PRD 5.1). All new columns are nullable or defaulted so this is a
zero-downtime, backward-compatible migration against existing rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0002_entitlements_and_catalog"
down_revision: str | None = "0001_initial_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def has_constraint(table_name: str, constraint_name: str) -> bool:
    # op.create_check_constraint runs the bare name through the same
    # naming_convention as the ORM models (see env.py's target_metadata),
    # so the constraint actually lands in the DB as "ck_<table>_<name>".
    inspector = inspect(op.get_bind())
    names = {c["name"] for c in inspector.get_check_constraints(table_name)}
    names |= {c["name"] for c in inspector.get_unique_constraints(table_name)}
    return constraint_name in names or f"ck_{table_name}_{constraint_name}" in names


def upgrade() -> None:
    if not has_column("users", "password_hash"):
        op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))

    if not has_column("strategies", "description"):
        op.add_column("strategies", sa.Column("description", sa.Text(), nullable=True))
    if not has_column("strategies", "timeframe"):
        op.add_column("strategies", sa.Column("timeframe", sa.String(8), nullable=True))
    if not has_column("strategies", "price"):
        op.add_column("strategies", sa.Column("price", sa.Numeric(18, 2), nullable=True))
    if not has_column("strategies", "profit_share_percent"):
        op.add_column(
            "strategies", sa.Column("profit_share_percent", sa.Numeric(5, 2), nullable=True)
        )
    if not has_column("strategies", "base_lot"):
        op.add_column("strategies", sa.Column("base_lot", sa.Numeric(18, 2), nullable=True))
    if not has_constraint("strategies", "price_non_negative"):
        op.create_check_constraint(
            "price_non_negative", "strategies", "price IS NULL OR price >= 0"
        )
    if not has_constraint("strategies", "profit_share_percent_in_range"):
        op.create_check_constraint(
            "profit_share_percent_in_range",
            "strategies",
            "profit_share_percent IS NULL "
            "OR (profit_share_percent >= 0 AND profit_share_percent <= 100)",
        )
    if not has_constraint("strategies", "base_lot_positive"):
        op.create_check_constraint(
            "base_lot_positive", "strategies", "base_lot IS NULL OR base_lot > 0"
        )

    if not has_column("strategy_assignments", "purchased_at"):
        op.add_column(
            "strategy_assignments",
            sa.Column("purchased_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not has_column("strategy_assignments", "expires_at"):
        op.add_column(
            "strategy_assignments", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
        )
    if not has_column("strategy_assignments", "payment_status"):
        op.add_column(
            "strategy_assignments",
            sa.Column("payment_status", sa.String(16), nullable=False, server_default="GRANTED"),
        )
    if not has_constraint("strategy_assignments", "payment_status_allowed"):
        op.create_check_constraint(
            "payment_status_allowed",
            "strategy_assignments",
            "payment_status IN ('GRANTED', 'REVOKED')",
        )

    if not has_column("executions", "entry_price"):
        op.add_column("executions", sa.Column("entry_price", sa.Numeric(18, 8), nullable=True))
    if not has_column("executions", "exit_price"):
        op.add_column("executions", sa.Column("exit_price", sa.Numeric(18, 8), nullable=True))
    if not has_column("executions", "realized_pnl"):
        op.add_column("executions", sa.Column("realized_pnl", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("executions", "realized_pnl")
    op.drop_column("executions", "exit_price")
    op.drop_column("executions", "entry_price")

    op.drop_constraint("payment_status_allowed", "strategy_assignments", type_="check")
    op.drop_column("strategy_assignments", "payment_status")
    op.drop_column("strategy_assignments", "expires_at")
    op.drop_column("strategy_assignments", "purchased_at")

    op.drop_constraint("base_lot_positive", "strategies", type_="check")
    op.drop_constraint("profit_share_percent_in_range", "strategies", type_="check")
    op.drop_constraint("price_non_negative", "strategies", type_="check")
    op.drop_column("strategies", "base_lot")
    op.drop_column("strategies", "profit_share_percent")
    op.drop_column("strategies", "price")
    op.drop_column("strategies", "timeframe")
    op.drop_column("strategies", "description")

    op.drop_column("users", "password_hash")
