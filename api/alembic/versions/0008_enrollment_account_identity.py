"""Enforce one broker identity and execution route per enrollment account.

Revision ID: 0008_enrollment_account_identity
Revises: 0007_marketplace_enrollments
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008_enrollment_account_identity"
down_revision: str | None = "0007_marketplace_enrollments"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Login is an account identifier, never a password. Existing rows remain
    # nullable until their account owner re-saves the credentials.
    op.add_column("enrollment_accounts", sa.Column("broker_login", sa.String(length=80)))
    op.create_unique_constraint(
        "uq_enrollment_accounts_server_broker_login",
        "enrollment_accounts",
        ["server_identifier", "broker_login"],
    )
    op.create_index(
        "uq_enrollment_accounts_external_account_ref",
        "enrollment_accounts",
        ["external_account_ref"],
        unique=True,
        postgresql_where=sa.text("external_account_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_enrollment_accounts_external_account_ref", table_name="enrollment_accounts")
    op.drop_constraint(
        "uq_enrollment_accounts_server_broker_login",
        "enrollment_accounts",
        type_="unique",
    )
    op.drop_column("enrollment_accounts", "broker_login")
