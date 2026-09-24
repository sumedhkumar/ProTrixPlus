"""user_role_grants + admin_invites

Revision ID: 0009_admin_invites_and_multirole
Revises: 0008_admin_role_tiers
Create Date: 2026-09-24

Two additive tables:
* ``user_role_grants`` - admin roles a user holds in addition to their
  primary ``users.role``, so one account can hold multiple admin tiers.
* ``admin_invites`` - hashed-token email invites for new/promoted admin
  accounts, same shape as ``password_reset_tokens`` (see that table's
  docstring in protrix_contracts.db.models for why the hash is unsalted).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "0009_admin_invites_and_multirole"
down_revision: str | None = "0008_admin_role_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = (
    "USER",
    "SUPER_ADMIN",
    "OPERATIONS_ADMIN",
    "STRATEGY_ADMIN",
    "FINANCE_ADMIN",
    "AUDITOR",
)


def _role_in_clause() -> str:
    return ", ".join(f"'{r}'" for r in _ROLES)


def upgrade() -> None:
    inspector = inspect(op.get_bind())

    if not inspector.has_table("user_role_grants"):
        op.create_table(
            "user_role_grants",
            sa.Column(
                "user_id",
                sa.Uuid(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("role", sa.String(20), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                f"role IN ({_role_in_clause()})", name="user_role_grants_role_allowed"
            ),
        )

    if not inspector.has_table("admin_invites"):
        op.create_table(
            "admin_invites",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("invited_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_table("admin_invites")
    op.drop_table("user_role_grants")
