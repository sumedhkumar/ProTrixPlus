"""add one-account-per-user execution scope

The initial release intentionally permits one hedging account per user.  The
account row holds transport metadata and an opaque credential reference only;
credentials remain outside the application database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "0003_trading_account_scope"
down_revision: str | None = "0002_rent_wallet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(bind: sa.Connection, name: str) -> bool:
    return context.is_offline_mode() or sa.inspect(bind).has_table(name)


def _needs_create(bind: sa.Connection, name: str) -> bool:
    return context.is_offline_mode() or not _has_table(bind, name)


def upgrade() -> None:
    bind = op.get_bind()
    if _needs_create(bind, "trading_accounts"):
        op.create_table(
            "trading_accounts",
            sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("provider_name", sa.String(length=120), nullable=False),
            sa.Column("server_identifier", sa.String(length=160), nullable=True),
            sa.Column("category", sa.String(length=12), nullable=False),
            sa.Column("transport", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("external_account_ref", sa.String(length=160), nullable=True),
            sa.Column("credential_key_ref", sa.String(length=160), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "category IN ('DEMO', 'LIVE')", name="ck_trading_accounts_category_allowed"
            ),
            sa.CheckConstraint(
                "transport IN ('MOCK', 'NATIVE_MT5', 'METAAPI')",
                name="ck_trading_accounts_transport_allowed",
            ),
            sa.CheckConstraint(
                "status IN ('ACTIVE', 'DISABLED')", name="ck_trading_accounts_status_allowed"
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], name="fk_trading_accounts_user_id_users"
            ),
            sa.PrimaryKeyConstraint("id", name="pk_trading_accounts"),
            sa.UniqueConstraint("user_id", name="uq_trading_accounts_user_id"),
        )

    # Account IDs deliberately match their user UUIDs. This deterministic
    # backfill works for every existing local database without a UUID extension
    # and keeps one account as the non-negotiable first-release boundary.
    op.execute(
        """
        INSERT INTO trading_accounts
            (id, user_id, provider_name, server_identifier, category, transport, status, credential_key_ref)
        SELECT id, id, 'Local development', 'MOCK_SERVER', 'DEMO', 'MOCK', 'ACTIVE',
               'local-profile:' || email
        FROM users
        ON CONFLICT (id) DO NOTHING
        """
    )



def downgrade() -> None:
    if _has_table(op.get_bind(), "trading_accounts"):
        op.drop_table("trading_accounts")
