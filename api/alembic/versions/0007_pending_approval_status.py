"""strategy_assignments.status gains PENDING_APPROVAL

Revision ID: 0007_pending_approval_status
Revises: 0006_vault_secrets
Create Date: 2026-09-23

Strategy subscription is self-service (a client can request any published
strategy without an admin), but a request must not be actionable until an
admin confirms the strategy's subscription price was actually paid. A new
self-subscribe request now starts at PENDING_APPROVAL - locked, no Setup
Wizard access - and only an admin moving it to SETUP_INCOMPLETE (this
migration's existing value) unlocks it. Existing rows are untouched; this
only widens what values are allowed and what the application chooses to
write. Follows 0006_alerts_setup_gate's idempotent/guarded style so this is
safe to run against a DB that already has the constraint from a different
provisioning path.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import inspect

from alembic import op

revision: str = "0007_pending_approval_status"
down_revision: str | None = "0006_vault_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW = "status IN ('PENDING_APPROVAL', 'SETUP_INCOMPLETE', 'ACTIVE', 'PAUSED')"
_OLD = "status IN ('SETUP_INCOMPLETE', 'ACTIVE', 'PAUSED')"


def _status_allows_pending_approval() -> bool:
    inspector = inspect(op.get_bind())
    for c in inspector.get_check_constraints("strategy_assignments"):
        if c["name"] in ("status_allowed", "ck_strategy_assignments_status_allowed"):
            return "PENDING_APPROVAL" in (c.get("sqltext") or "")
    return False


def upgrade() -> None:
    if not _status_allows_pending_approval():
        op.drop_constraint("status_allowed", "strategy_assignments", type_="check")
        op.create_check_constraint("status_allowed", "strategy_assignments", _NEW)


def downgrade() -> None:
    op.drop_constraint("status_allowed", "strategy_assignments", type_="check")
    op.create_check_constraint("status_allowed", "strategy_assignments", _OLD)
