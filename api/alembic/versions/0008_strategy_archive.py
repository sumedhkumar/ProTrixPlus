"""strategies gains is_archived

Revision ID: 0008_strategy_archive
Revises: 0007_pending_approval_status
Create Date: 2026-09-27

"Remove from the admin panel" for a strategy with real trading history
(assignments/order-intents/signals) can't mean a hard DELETE - the
strategy_assignments and order_intents FKs to strategies.id have no
ondelete=CASCADE, so that would either be rejected by the DB or destroy
real trade history. Archiving instead: is_archived=True hides the row from
both the admin catalog and the client marketplace (marketplace.list_catalog
now filters it out by default) while every assignment/order-intent/signal
referencing it stays intact, and it's reversible via
marketplace.admin_unarchive_strategy. Follows 0006/0007's idempotent style.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0008_strategy_archive"
down_revision: str | None = "0007_pending_approval_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def has_column(table_name: str, column_name: str) -> bool:
    inspector = inspect(op.get_bind())
    return any(c["name"] == column_name for c in inspector.get_columns(table_name))


def upgrade() -> None:
    if not has_column("strategies", "is_archived"):
        op.add_column(
            "strategies",
            sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    if has_column("strategies", "is_archived"):
        op.drop_column("strategies", "is_archived")
