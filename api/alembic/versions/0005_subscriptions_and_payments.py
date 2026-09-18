"""account-level subscriptions, payment submissions, password reset tokens

Revision ID: 0005_subscriptions_and_payments
Revises: 0004_strategy_symbol
Create Date: 2026-09-18

Adds account-level subscription tracking to `users` (phone,
must_change_password, subscription_package/start/end - distinct from the
existing per-*strategy* `strategy_assignments.expires_at`), a
`payment_submissions` table for manually-reviewed UTR/transaction-reference
proof of payment on paid packages, and a `password_reset_tokens` table for
the self-service forgot-password flow. All new `users` columns are
nullable-or-defaulted, so this is zero-downtime against existing rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_subscriptions_and_payments"
down_revision: str | None = "0004_strategy_symbol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(32), nullable=True))
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("users", sa.Column("subscription_package", sa.String(16), nullable=True))
    op.add_column(
        "users", sa.Column("subscription_start", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("subscription_end", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "subscription_package_allowed",
        "users",
        "subscription_package IS NULL "
        "OR subscription_package IN ('TRIAL_7D', 'PLAN_3M', 'PLAN_6M', 'PLAN_12M')",
    )

    op.create_table(
        "payment_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(32), nullable=False),
        sa.Column("package", sa.String(16), nullable=False),
        sa.Column("utr_reference", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column(
            "submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("package IN ('PLAN_3M', 'PLAN_6M', 'PLAN_12M')", name="package_allowed"),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="status_allowed"),
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("payment_submissions")

    op.drop_constraint("subscription_package_allowed", "users", type_="check")
    op.drop_column("users", "subscription_end")
    op.drop_column("users", "subscription_start")
    op.drop_column("users", "subscription_package")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "phone")
