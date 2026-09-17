"""add immutable rent settlements and wallet ledger

The S0 ``0001`` migration creates the initial schema from shared metadata.
Because that migration is intentionally metadata-driven, this migration is
safe both for databases upgraded from the original S0 models and for a fresh
database where ``0001`` already saw the new tables. The mutation guards are
installed in both cases.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0002_rent_wallet"
down_revision: str | None = "0001_initial_skeleton"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FINANCIAL_GUARD = """
CREATE OR REPLACE FUNCTION rent_financial_records_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only (attempted %)', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS settlements_no_update_delete ON settlements;
CREATE TRIGGER settlements_no_update_delete
    BEFORE UPDATE OR DELETE ON settlements
    FOR EACH ROW EXECUTE FUNCTION rent_financial_records_block_mutation();

DROP TRIGGER IF EXISTS rent_ledger_entries_no_update_delete ON rent_ledger_entries;
CREATE TRIGGER rent_ledger_entries_no_update_delete
    BEFORE UPDATE OR DELETE ON rent_ledger_entries
    FOR EACH ROW EXECUTE FUNCTION rent_financial_records_block_mutation();
"""

_FINANCIAL_GUARD_DROP = """
DROP TRIGGER IF EXISTS rent_ledger_entries_no_update_delete ON rent_ledger_entries;
DROP TRIGGER IF EXISTS settlements_no_update_delete ON settlements;
DROP FUNCTION IF EXISTS rent_financial_records_block_mutation();
"""


def _has_table(bind: sa.Connection, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _needs_create(bind: sa.Connection, name: str) -> bool:
    # Offline SQL generation has no inspectable database state. The initial
    # snapshot now excludes these tables, so emitting CREATE TABLE is correct.
    return context.is_offline_mode() or not _has_table(bind, name)


def upgrade() -> None:
    bind = op.get_bind()

    if _needs_create(bind, "settlements"):
        op.create_table(
            "settlements",
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("cadence", sa.String(length=8), nullable=False, server_default="DAILY"),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("net_closed_realized_pnl", sa.Numeric(18, 8), nullable=False),
            sa.Column("rent_rate", sa.Numeric(9, 6), nullable=False),
            sa.Column("rent_due", sa.Numeric(18, 8), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("idempotency_key", sa.String(length=256), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "cadence IN ('DAILY', 'WEEKLY')",
                name="ck_settlements_cadence_allowed",
            ),
            sa.CheckConstraint(
                "period_end > period_start",
                name="ck_settlements_period_bounds_ordered",
            ),
            sa.CheckConstraint(
                "rent_rate >= 0 AND rent_rate <= 1",
                name="ck_settlements_rent_rate_between_zero_and_one",
            ),
            sa.CheckConstraint("rent_due >= 0", name="ck_settlements_rent_due_non_negative"),
            sa.CheckConstraint("currency = 'USD'", name="ck_settlements_currency_usd"),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name="fk_settlements_user_id_users",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_settlements"),
            sa.UniqueConstraint(
                "user_id",
                "cadence",
                "period_start",
                name="uq_settlements_user_cadence_period_start",
            ),
            sa.UniqueConstraint("idempotency_key", name="uq_settlements_idempotency_key"),
        )

    if _needs_create(bind, "rent_ledger_entries"):
        op.create_table(
            "rent_ledger_entries",
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("settlement_id", sa.Uuid(as_uuid=True), nullable=True),
            sa.Column("entry_type", sa.String(length=16), nullable=False),
            sa.Column("amount", sa.Numeric(18, 8), nullable=False),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("idempotency_key", sa.String(length=256), nullable=False),
            sa.Column("source_ref", sa.String(length=128), nullable=True),
            sa.Column("reason", sa.String(length=240), nullable=True),
            sa.Column("actor", sa.String(length=120), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "entry_type IN ('TOP_UP', 'RENT_CHARGE', 'ADJUSTMENT', 'REVERSAL')",
                name="ck_rent_ledger_entries_entry_type_allowed",
            ),
            sa.CheckConstraint(
                "amount <> 0",
                name="ck_rent_ledger_entries_amount_non_zero",
            ),
            sa.CheckConstraint(
                "(entry_type <> 'RENT_CHARGE') OR (amount < 0)",
                name="ck_rent_ledger_entries_rent_charge_negative",
            ),
            sa.CheckConstraint(
                "(entry_type <> 'TOP_UP') OR (amount > 0)",
                name="ck_rent_ledger_entries_top_up_positive",
            ),
            sa.CheckConstraint(
                "(entry_type <> 'RENT_CHARGE') OR (settlement_id IS NOT NULL)",
                name="ck_rent_ledger_entries_rent_charge_has_settlement",
            ),
            sa.CheckConstraint(
                "currency = 'USD'",
                name="ck_rent_ledger_entries_currency_usd",
            ),
            sa.ForeignKeyConstraint(
                ["settlement_id"],
                ["settlements.id"],
                name="fk_rent_ledger_entries_settlement_id_settlements",
            ),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name="fk_rent_ledger_entries_user_id_users",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_rent_ledger_entries"),
            sa.UniqueConstraint(
                "settlement_id",
                "entry_type",
                name="uq_rent_ledger_entries_settlement_entry_type",
            ),
            sa.UniqueConstraint(
                "idempotency_key",
                name="uq_rent_ledger_entries_idempotency_key",
            ),
        )

    op.execute(_FINANCIAL_GUARD)


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(_FINANCIAL_GUARD_DROP)
    if context.is_offline_mode() or _has_table(bind, "rent_ledger_entries"):
        op.drop_table("rent_ledger_entries")
    if context.is_offline_mode() or _has_table(bind, "settlements"):
        op.drop_table("settlements")
