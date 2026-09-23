"""strategies.min_balance

Revision ID: 0007_strategy_min_balance
Revises: 0006_vault_secrets
Create Date: 2026-09-23

Strategy eligibility (task 1.10): the minimum MT5 account balance a client
needs for this strategy to work. Admin-set on the catalog entry, like price/
base_lot/win_rate. Nullable/backward-compatible - existing strategies have no
minimum until an admin sets one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0007_strategy_min_balance"
down_revision: str | None = "0006_vault_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if any(c["name"] == "min_balance" for c in inspector.get_columns("strategies")):
        return
    op.add_column("strategies", sa.Column("min_balance", sa.Numeric(18, 2), nullable=True))
    op.create_check_constraint(
        "min_balance_non_negative", "strategies", "min_balance IS NULL OR min_balance >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("min_balance_non_negative", "strategies", type_="check")
    op.drop_column("strategies", "min_balance")
