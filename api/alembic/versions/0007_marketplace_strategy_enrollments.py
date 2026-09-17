"""Add isolated marketplace strategy enrollments.

The pre-existing MVP tables remain intact for the native-demo route.  New
marketplace purchases use the enrollment tables, which makes one MT5 account
and one escrow wallet independent for every user/strategy pair.

Revision ID: 0007_marketplace_enrollments
Revises: 0006_account_worker_heartbeat
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_marketplace_enrollments"
down_revision: str | None = "0006_account_worker_heartbeat"
branch_labels: str | None = None
depends_on: str | None = None


def _uuid() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False)


def upgrade() -> None:
    op.create_table(
        "strategy_offers",
        _uuid(),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("platform_fee_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("escrow_credit_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("minimum_wallet_usd", sa.Numeric(18, 8), nullable=False, server_default="10.00"),
        sa.Column("profit_share_rate", sa.Numeric(9, 6), nullable=False, server_default="0.10"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.UniqueConstraint("strategy_id", name="uq_strategy_offers_strategy_id"),
        sa.CheckConstraint("price_usd > 0", name="price_usd_positive"),
        sa.CheckConstraint("platform_fee_usd >= 0", name="platform_fee_usd_non_negative"),
        sa.CheckConstraint("escrow_credit_usd >= 0", name="escrow_credit_usd_non_negative"),
        sa.CheckConstraint("platform_fee_usd + escrow_credit_usd = price_usd", name="offer_split_matches_price"),
        sa.CheckConstraint("duration_days > 0", name="duration_days_positive"),
        sa.CheckConstraint("minimum_wallet_usd >= 0", name="minimum_wallet_usd_non_negative"),
        sa.CheckConstraint("profit_share_rate >= 0 AND profit_share_rate <= 1", name="profit_share_rate_between_zero_and_one"),
    )
    op.create_table(
        "strategy_enrollments",
        _uuid(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="CREDENTIALS_REQUIRED"),
        sa.Column("minimum_wallet_usd", sa.Numeric(18, 8), nullable=False, server_default="10.00"),
        sa.Column("profit_share_rate", sa.Numeric(9, 6), nullable=False, server_default="0.10"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.UniqueConstraint("user_id", "strategy_id", name="uq_strategy_enrollments_user_strategy"),
        sa.CheckConstraint("status IN ('CREDENTIALS_REQUIRED', 'ACTIVE', 'PAUSED', 'EXPIRED', 'DISABLED')", name="status_allowed"),
        sa.CheckConstraint("minimum_wallet_usd >= 0", name="minimum_wallet_usd_non_negative"),
        sa.CheckConstraint("profit_share_rate >= 0 AND profit_share_rate <= 1", name="profit_share_rate_between_zero_and_one"),
    )
    op.create_table(
        "enrollment_accounts",
        _uuid(),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(120), nullable=False),
        sa.Column("server_identifier", sa.String(160)),
        sa.Column("category", sa.String(12), nullable=False, server_default="DEMO"),
        sa.Column("transport", sa.String(16), nullable=False, server_default="MOCK"),
        sa.Column("status", sa.String(16), nullable=False, server_default="DISABLED"),
        sa.Column("external_account_ref", sa.String(160)),
        sa.Column("credential_key_ref", sa.String(160)),
        sa.Column("worker_adapter", sa.String(32)),
        sa.Column("worker_name", sa.String(120)),
        sa.Column("worker_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["enrollment_id"], ["strategy_enrollments.id"]),
        sa.UniqueConstraint("enrollment_id", name="uq_enrollment_accounts_enrollment_id"),
        sa.CheckConstraint("category IN ('DEMO', 'LIVE')", name="category_allowed"),
        sa.CheckConstraint("transport IN ('MOCK', 'NATIVE_MT5', 'METAAPI')", name="transport_allowed"),
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status_allowed"),
    )
    op.create_table(
        "strategy_purchases",
        _uuid(),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("price_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("platform_fee_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("escrow_credit_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("razorpay_order_id", sa.String(80)),
        sa.Column("razorpay_payment_id", sa.String(80)),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["enrollment_id"], ["strategy_enrollments.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_strategy_purchases_idempotency_key"),
        sa.UniqueConstraint("razorpay_order_id", name="uq_strategy_purchases_razorpay_order_id"),
        sa.UniqueConstraint("razorpay_payment_id"),
        sa.CheckConstraint("source IN ('RAZORPAY', 'ADMIN')", name="source_allowed"),
        sa.CheckConstraint("status IN ('PENDING', 'PAID', 'FAILED', 'REFUND_REVIEW')", name="status_allowed"),
        sa.CheckConstraint("price_usd > 0", name="price_usd_positive"),
        sa.CheckConstraint("platform_fee_usd + escrow_credit_usd = price_usd", name="purchase_split_matches_price"),
        sa.CheckConstraint("ends_at > starts_at", name="period_ordered"),
    )
    op.create_table(
        "strategy_settlements",
        _uuid(),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_closed_realized_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("profit_share_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("profit_share_due", sa.Numeric(18, 8), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["enrollment_id"], ["strategy_enrollments.id"]),
        sa.UniqueConstraint("enrollment_id", "period_start", name="uq_strategy_settlements_enrollment_period_start"),
        sa.UniqueConstraint("idempotency_key", name="uq_strategy_settlements_idempotency_key"),
        sa.CheckConstraint("period_end > period_start", name="period_bounds_ordered"),
        sa.CheckConstraint("profit_share_rate >= 0 AND profit_share_rate <= 1", name="profit_share_rate_between_zero_and_one"),
        sa.CheckConstraint("profit_share_due >= 0", name="profit_share_due_non_negative"),
    )
    op.create_table(
        "payment_orders",
        _uuid(),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True)),
        sa.Column("purpose", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("amount_usd", sa.Numeric(18, 8), nullable=False),
        sa.Column("razorpay_order_id", sa.String(80)),
        sa.Column("razorpay_payment_id", sa.String(80)),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["enrollment_id"], ["strategy_enrollments.id"]),
        sa.ForeignKeyConstraint(["purchase_id"], ["strategy_purchases.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_orders_idempotency_key"),
        sa.UniqueConstraint("razorpay_order_id", name="uq_payment_orders_razorpay_order_id"),
        sa.UniqueConstraint("razorpay_payment_id"),
        sa.CheckConstraint("purpose IN ('STRATEGY_PURCHASE', 'WALLET_TOP_UP')", name="purpose_allowed"),
        sa.CheckConstraint("status IN ('PENDING', 'PAID', 'FAILED', 'REFUND_REVIEW')", name="status_allowed"),
        sa.CheckConstraint("amount_usd > 0", name="amount_usd_positive"),
    )
    op.create_table(
        "payment_events",
        _uuid(),
        sa.Column("provider_event_id", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider_event_id", name="uq_payment_events_provider_event_id"),
    )
    op.create_table(
        "escrow_ledger_entries",
        _uuid(),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_id", postgresql.UUID(as_uuid=True)),
        sa.Column("settlement_id", postgresql.UUID(as_uuid=True)),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("idempotency_key", sa.String(256), nullable=False),
        sa.Column("reason", sa.String(240)),
        sa.Column("actor", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["enrollment_id"], ["strategy_enrollments.id"]),
        sa.ForeignKeyConstraint(["purchase_id"], ["strategy_purchases.id"]),
        sa.ForeignKeyConstraint(["settlement_id"], ["strategy_settlements.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_escrow_ledger_entries_idempotency_key"),
        sa.CheckConstraint("amount <> 0", name="amount_non_zero"),
        sa.CheckConstraint("currency = 'USD'", name="currency_usd"),
    )
    op.create_table(
        "closed_trade_attributions",
        _uuid(),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker_deal_id", sa.String(128), nullable=False),
        sa.Column("broker_position_ref", sa.String(128), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_realized_pnl", sa.Numeric(18, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["enrollment_id"], ["strategy_enrollments.id"]),
        sa.UniqueConstraint("enrollment_id", "broker_deal_id", name="uq_closed_trade_attributions_enrollment_deal"),
    )
    op.add_column("order_intents", sa.Column("enrollment_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_order_intents_enrollment_id_strategy_enrollments",
        "order_intents",
        "strategy_enrollments",
        ["enrollment_id"],
        ["id"],
    )
    op.add_column(
        "mock_broker_deals",
        sa.Column("account_ref", sa.String(length=160), nullable=False, server_default="legacy"),
    )


def downgrade() -> None:
    op.drop_column("mock_broker_deals", "account_ref")
    op.drop_constraint("fk_order_intents_enrollment_id_strategy_enrollments", "order_intents", type_="foreignkey")
    op.drop_column("order_intents", "enrollment_id")
    for table in (
        "closed_trade_attributions",
        "escrow_ledger_entries",
        "payment_events",
        "payment_orders",
        "strategy_settlements",
        "strategy_purchases",
        "enrollment_accounts",
        "strategy_enrollments",
        "strategy_offers",
    ):
        op.drop_table(table)
