"""signals.duplicate_attempts

Revision ID: 0005_signal_duplicate_attempts
Revises: 0005_subscriptions_and_payments
Create Date: 2026-09-18

Phase 10 ops visibility: count how many times each signal_id was re-delivered
as a genuine duplicate (idempotency-key hit with a matching hash), so an
admin can see it instead of it only ever showing up in logs. Additive,
backward-compatible - server_default keeps every existing row at 0.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_signal_duplicate_attempts"
down_revision: str | None = "0005_subscriptions_and_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("duplicate_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("signals", "duplicate_attempts")
