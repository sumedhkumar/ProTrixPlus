"""Store last-seen native execution worker state per account.

Revision ID: 0006_account_worker_heartbeat
Revises: 0005_directional_reversal
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0006_account_worker_heartbeat"
down_revision: str | None = "0005_directional_reversal"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("trading_accounts", sa.Column("worker_adapter", sa.String(length=32)))
    op.add_column("trading_accounts", sa.Column("worker_name", sa.String(length=120)))
    op.add_column("trading_accounts", sa.Column("worker_heartbeat_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("trading_accounts", "worker_heartbeat_at")
    op.drop_column("trading_accounts", "worker_name")
    op.drop_column("trading_accounts", "worker_adapter")
