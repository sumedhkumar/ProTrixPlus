"""initial skeleton schema

Revision ID: 0001_initial_skeleton
Revises:
Create Date: 2026-09-08

The nine tables S0 provisioned, frozen as explicit DDL.

This migration used to call ``target_metadata.create_all()`` against the shared
metadata in ``protrix_contracts.db`` - the idea being that the migration could
never drift from the models. In practice it did the opposite: ``target_metadata``
is not a snapshot of the schema at this revision, it is whatever the ORM models
say *today*. So on a fresh database this step created the entire current schema,
and every later migration then found its objects already present and had to be
retrofitted with "does this exist yet?" guards. ``0006_alerts_setup_gate`` was
written without those guards and crash-looped the Render deploy on
``DuplicateTable: relation "alerts" already exists``.

The DDL below was generated from the models as of commit f5d9ac5, the commit
that introduced this revision, so it creates exactly what S0 created and nothing
that came after. Constraint and index names are left to the metadata naming
convention (see ``protrix_contracts.db.base.NAMING_CONVENTION``), which Alembic
applies to ``op.*`` calls via ``target_metadata`` in env.py - hence the bare
check-constraint names here.

On top of the tables this also installs a trigger that makes ``audit_events``
insert-only (UPDATE / DELETE raise).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_skeleton"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_events_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is insert-only (attempted %)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation();
"""

_AUDIT_GUARD_DROP = """
DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events;
DROP FUNCTION IF EXISTS audit_events_block_mutation();
"""


def upgrade() -> None:
    # --- tables with no outbound foreign keys ----------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("role IN ('USER', 'SUPER_ADMIN')", name="role_allowed"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("strategy_key", "strategy_version"),
    )

    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("payload_hash", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(8), nullable=False),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("strategy_version", sa.String(32), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("position_ref", sa.String(128), nullable=True),
        sa.Column("close_fraction", sa.Numeric(9, 4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(18, 8), nullable=True),
        sa.Column("take_profit", sa.Numeric(18, 8), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("event_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("signal_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_signals_payload_hash", "signals", ["payload_hash"])
    op.create_index("ix_signals_strategy", "signals", ["strategy_key", "strategy_version"])

    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(48), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("status IN ('PENDING', 'PUBLISHED', 'FAILED')", name="status_allowed"),
    )
    op.create_index("ix_outbox_dispatch", "outbox", ["status", "available_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("actor", sa.String(120), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "mock_broker_deals",
        sa.Column("client_order_id", sa.String(64), primary_key=True),
        sa.Column("ticket_id", sa.String(64), nullable=False),
        sa.Column("deal_id", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("volume", sa.Numeric(18, 2), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # --- tables with foreign keys into the above -------------------------
    op.create_table(
        "strategy_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column("master_lot", sa.Numeric(18, 2), nullable=False),
        sa.Column("multiplier", sa.Numeric(9, 4), nullable=False),
        sa.Column("multiplier_min", sa.Numeric(9, 4), nullable=False),
        sa.Column("multiplier_max", sa.Numeric(9, 4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "strategy_id"),
        sa.CheckConstraint("master_lot > 0", name="master_lot_positive"),
        sa.CheckConstraint("multiplier_min > 0", name="multiplier_min_positive"),
        sa.CheckConstraint("multiplier_min <= multiplier_max", name="multiplier_bounds_ordered"),
        sa.CheckConstraint(
            "multiplier >= multiplier_min AND multiplier <= multiplier_max",
            name="multiplier_within_bounds",
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'PAUSED')", name="status_allowed"),
    )

    op.create_table(
        "order_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column(
            "signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=False
        ),
        sa.Column("command_target", sa.String(16), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("computed_lot", sa.Numeric(18, 2), nullable=False),
        sa.Column("master_lot", sa.Numeric(18, 2), nullable=False),
        sa.Column("multiplier", sa.Numeric(9, 4), nullable=False),
        sa.Column("eligibility_status", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("user_id", "strategy_id", "signal_id", "command_target"),
        sa.CheckConstraint("computed_lot > 0", name="computed_lot_positive"),
        sa.CheckConstraint("status IN ('CREATED', 'EXECUTING', 'SETTLED')", name="status_allowed"),
    )

    op.create_table(
        "executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_intent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("order_intents.id"),
            nullable=False,
        ),
        sa.Column("client_order_id", sa.String(64), nullable=False),
        sa.Column("adapter", sa.String(48), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("ticket_id", sa.String(64), nullable=True),
        sa.Column("deal_id", sa.String(64), nullable=True),
        sa.Column("reconcile_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intent_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_queue_ms", sa.Integer(), nullable=True),
        sa.Column("latency_dispatch_ms", sa.Integer(), nullable=True),
        sa.Column("latency_ack_ms", sa.Integer(), nullable=True),
        sa.Column("latency_fill_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("order_intent_id"),
        sa.UniqueConstraint("client_order_id"),
        sa.CheckConstraint("reconcile_count >= 0", name="reconcile_count_non_negative"),
    )

    op.execute(_AUDIT_GUARD)


def downgrade() -> None:
    op.execute(_AUDIT_GUARD_DROP)
    op.drop_table("executions")
    op.drop_table("order_intents")
    op.drop_table("strategy_assignments")
    op.drop_table("mock_broker_deals")
    op.drop_table("audit_events")
    op.drop_index("ix_outbox_dispatch", table_name="outbox")
    op.drop_table("outbox")
    op.drop_index("ix_signals_strategy", table_name="signals")
    op.drop_index("ix_signals_payload_hash", table_name="signals")
    op.drop_table("signals")
    op.drop_table("strategies")
    op.drop_table("users")
