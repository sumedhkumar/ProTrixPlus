"""add MVP subscriptions, risk controls, and managed-position attribution"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0004_mvp_controls_and_positions"
down_revision: str | None = "0003_trading_account_scope"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _needs_create(bind: sa.Connection, name: str) -> bool:
    return context.is_offline_mode() or not sa.inspect(bind).has_table(name)


def _create(name: str, *columns: sa.Column[object], constraints: list[sa.Constraint]) -> None:
    if _needs_create(op.get_bind(), name):
        op.create_table(name, *columns, *constraints)


def upgrade() -> None:
    _create(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        constraints=[
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.UniqueConstraint("user_id", name="uq_subscriptions_user_id"),
            sa.CheckConstraint("status IN ('ACTIVE', 'EXPIRED', 'DISABLED')", name="status_allowed"),
            sa.CheckConstraint("ends_at > starts_at", name="period_ordered"),
        ],
    )
    _create(
        "trading_controls",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("admin_suspended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("risk_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        constraints=[
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.UniqueConstraint("user_id", name="uq_trading_controls_user_id"),
        ],
    )
    _create(
        "risk_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("max_lot", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_open_trades", sa.Integer(), nullable=False),
        sa.Column("max_daily_loss", sa.Numeric(18, 8), nullable=False),
        sa.Column("allowed_symbols", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        constraints=[
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.UniqueConstraint("user_id", name="uq_risk_profiles_user_id"),
            sa.CheckConstraint("max_lot > 0", name="max_lot_positive"),
            sa.CheckConstraint("max_open_trades > 0", name="max_open_trades_positive"),
            sa.CheckConstraint("max_daily_loss >= 0", name="max_daily_loss_non_negative"),
        ],
    )
    _create(
        "managed_positions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("strategy_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("entry_execution_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_position_ref", sa.String(128), nullable=False),
        sa.Column("broker_position_ref", sa.String(128), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("initial_volume", sa.Numeric(18, 2), nullable=False),
        sa.Column("remaining_volume", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        constraints=[
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
            sa.ForeignKeyConstraint(["entry_execution_id"], ["executions.id"]),
            sa.UniqueConstraint("entry_execution_id", name="uq_managed_positions_entry_execution_id"),
            sa.UniqueConstraint("user_id", "strategy_id", "source_position_ref", name="uq_managed_positions_source_ref"),
            sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="status_allowed"),
            sa.CheckConstraint("initial_volume > 0", name="initial_volume_positive"),
            sa.CheckConstraint("remaining_volume >= 0", name="remaining_volume_non_negative"),
        ],
    )


def downgrade() -> None:
    for name in ("managed_positions", "risk_profiles", "trading_controls", "subscriptions"):
        if sa.inspect(op.get_bind()).has_table(name):
            op.drop_table(name)
