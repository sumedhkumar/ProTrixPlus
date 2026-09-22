"""strategies.symbol

Revision ID: 0004_strategy_symbol
Revises: 0003_mt5_connections
Create Date: 2026-09-18

A strategy trades one instrument; this was missing, which is why the
"Simulate TV Signal" feature was hardcoded to EURUSD regardless of which
strategy was targeted. Nullable/backward-compatible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0004_strategy_symbol"
down_revision: str | None = "0003_mt5_connections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    if any(c["name"] == "symbol" for c in inspector.get_columns("strategies")):
        return
    op.add_column("strategies", sa.Column("symbol", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("strategies", "symbol")
