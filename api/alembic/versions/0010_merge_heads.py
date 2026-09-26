"""merge heads: archive/signal-status branch + RBAC/min-balance branch

Revision ID: 0010_merge_heads
Revises: 0008_strategy_archive, 0009_admin_invites_and_multirole
Create Date: 2026-09-26

Pure merge point, no schema change of its own - staging and this branch
each independently forked off 0006_vault_secrets (0007_pending_approval_status
-> 0008_strategy_archive here; 0007_strategy_min_balance ->
0008_admin_role_tiers -> 0009_admin_invites_and_multirole on staging),
so alembic had two real heads once the branches merged. This just joins
them back into one linear chain.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0010_merge_heads"
down_revision: str | None = ("0008_strategy_archive", "0009_admin_invites_and_multirole")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
