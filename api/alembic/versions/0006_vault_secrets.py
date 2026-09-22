"""vault_secrets

Revision ID: 0006_vault_secrets
Revises: 0005_signal_duplicate_attempts
Create Date: 2026-09-18

Backing store for RealCredentialVault (api/app/vault/real.py): encrypted-at-
rest credential handles that survive a process restart, unlike the in-memory
MockCredentialVault. Net-new table - nothing existing reads or writes it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_vault_secrets"
down_revision: str | None = "0005_signal_duplicate_attempts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vault_secrets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("handle_id", sa.String(64), nullable=False),
        sa.Column("key_id", sa.String(32), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("account_ref", sa.String(128), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("handle_id", name="uq_vault_secrets_handle_id"),
    )


def downgrade() -> None:
    op.drop_table("vault_secrets")
