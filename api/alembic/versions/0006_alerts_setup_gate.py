"""alerts catalog, setup-gate status, strategy marketing fields

Revision ID: 0006_alerts_setup_gate
Revises: 0005_mt5_connection_metaapi
Create Date: 2026-09-20

Three independent additions for the Strategy & Alert Management Platform
build:

1. `alerts` - an admin-authored TradingView alert-config catalog (name,
   symbol, lot_size, timeframe), optionally bundled into a strategy. Changes
   are diffed and recorded in the existing `audit_events` table
   (entity_type="alert") by the service layer - no new changelog table.
2. `strategy_assignments.status` gains a new SETUP_INCOMPLETE value, the
   default for brand-new admin grants going forward. Existing rows are left
   completely untouched by this migration - only new INSERTs (from
   marketplace.admin_grant_entitlement, in application code, not a DB
   default) will use it. Requires dropping and recreating the
   `status_allowed` CHECK constraint to allow the new value.
   `confirmed_risk_disclosure` / `activated_at` are set once, by
   marketplace.confirm_start, when the client completes the setup wizard's
   explicit risk-disclosure confirmation.
3. `strategies.win_rate` / `max_drawdown` / `description_short` - catalog
   display fields from the platform's Feature 2 spec. Display only; they
   never feed sizing or eligibility logic.

All new columns are nullable or defaulted - zero-downtime against existing
rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_alerts_setup_gate"
down_revision: str | None = "0005_mt5_connection_metaapi"
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


def _status_allows_setup_incomplete() -> bool:
    inspector = inspect(op.get_bind())
    for c in inspector.get_check_constraints("strategy_assignments"):
        if c["name"] in ("status_allowed", "ck_strategy_assignments_status_allowed"):
            return "SETUP_INCOMPLETE" in (c.get("sqltext") or "")
    return False


def upgrade() -> None:
    # Databases provisioned before 0001 was frozen to an explicit snapshot got
    # the whole then-current model set from its create_all(), so some of these
    # objects can already exist - same situation 0002-0005 guard against.
    if not inspect(op.get_bind()).has_table("alerts"):
        op.create_table(
            "alerts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "strategy_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("strategies.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("lot_size", sa.Numeric(18, 2), nullable=False),
            sa.Column("timeframe", sa.String(8), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_check_constraint("alert_lot_size_positive", "alerts", "lot_size > 0")
        op.create_index("ix_alerts_strategy_id", "alerts", ["strategy_id"])

    if not has_column("strategy_assignments", "confirmed_risk_disclosure"):
        op.add_column(
            "strategy_assignments",
            sa.Column(
                "confirmed_risk_disclosure",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if not has_column("strategy_assignments", "activated_at"):
        op.add_column(
            "strategy_assignments",
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _status_allows_setup_incomplete():
        op.drop_constraint("status_allowed", "strategy_assignments", type_="check")
        op.create_check_constraint(
            "status_allowed",
            "strategy_assignments",
            "status IN ('SETUP_INCOMPLETE', 'ACTIVE', 'PAUSED')",
        )

    if not has_column("strategies", "win_rate"):
        op.add_column("strategies", sa.Column("win_rate", sa.Numeric(5, 2), nullable=True))
    if not has_column("strategies", "max_drawdown"):
        op.add_column("strategies", sa.Column("max_drawdown", sa.Numeric(5, 2), nullable=True))
    if not has_column("strategies", "description_short"):
        op.add_column("strategies", sa.Column("description_short", sa.String(240), nullable=True))
    if not has_constraint("strategies", "win_rate_in_range"):
        op.create_check_constraint(
            "win_rate_in_range",
            "strategies",
            "win_rate IS NULL OR (win_rate >= 0 AND win_rate <= 100)",
        )
    if not has_constraint("strategies", "max_drawdown_in_range"):
        op.create_check_constraint(
            "max_drawdown_in_range",
            "strategies",
            "max_drawdown IS NULL OR (max_drawdown >= 0 AND max_drawdown <= 100)",
        )


def downgrade() -> None:
    op.drop_constraint("max_drawdown_in_range", "strategies", type_="check")
    op.drop_constraint("win_rate_in_range", "strategies", type_="check")
    op.drop_column("strategies", "description_short")
    op.drop_column("strategies", "max_drawdown")
    op.drop_column("strategies", "win_rate")

    op.drop_constraint("status_allowed", "strategy_assignments", type_="check")
    op.create_check_constraint(
        "status_allowed", "strategy_assignments", "status IN ('ACTIVE', 'PAUSED')"
    )
    op.drop_column("strategy_assignments", "activated_at")
    op.drop_column("strategy_assignments", "confirmed_risk_disclosure")

    op.drop_index("ix_alerts_strategy_id", table_name="alerts")
    op.drop_constraint("alert_lot_size_positive", "alerts", type_="check")
    op.drop_table("alerts")
