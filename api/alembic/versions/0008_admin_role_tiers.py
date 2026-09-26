"""users.role: add functional admin tiers

Revision ID: 0008_admin_role_tiers
Revises: 0007_strategy_min_balance
Create Date: 2026-09-24

Splits the flat SUPER_ADMIN-does-everything model into functional tiers
(OPERATIONS_ADMIN, STRATEGY_ADMIN, FINANCE_ADMIN, AUDITOR) so a given admin
account only needs the permissions its job requires. SUPER_ADMIN keeps doing
everything these can. See protrix_contracts.db.models.UserRole - this
migration only widens the `role_allowed` CHECK constraint to match.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_admin_role_tiers"
down_revision: str | None = "0007_strategy_min_balance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_ROLES = ("USER", "SUPER_ADMIN")
_NEW_ROLES = (
    "USER",
    "SUPER_ADMIN",
    "OPERATIONS_ADMIN",
    "STRATEGY_ADMIN",
    "FINANCE_ADMIN",
    "AUDITOR",
)


def _in_clause(roles: tuple[str, ...]) -> str:
    return ", ".join(f"'{r}'" for r in roles)


def upgrade() -> None:
    op.drop_constraint("role_allowed", "users", type_="check")
    op.create_check_constraint("role_allowed", "users", f"role IN ({_in_clause(_NEW_ROLES)})")


def downgrade() -> None:
    op.drop_constraint("role_allowed", "users", type_="check")
    op.create_check_constraint("role_allowed", "users", f"role IN ({_in_clause(_OLD_ROLES)})")
