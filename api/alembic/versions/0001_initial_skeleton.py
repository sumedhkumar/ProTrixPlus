"""initial skeleton schema

Revision ID: 0001_initial_skeleton
Revises:
Create Date: 2026-09-08

S0 provisions the whole schema directly from the shared SQLAlchemy metadata in
``protrix_contracts.db`` so the migration can never drift from the models that
api and worker map against. Later migrations will be explicit ``op.*`` deltas.

On top of the tables this also installs a trigger that makes ``audit_events``
insert-only (UPDATE / DELETE raise).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import MetaData
from alembic import op

from protrix_contracts.db import metadata as target_metadata

revision: str = "0001_initial_skeleton"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_events_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is insert-only (attempted %)', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutation();
"""

_AUDIT_GUARD_DROP = """
DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events;
DROP FUNCTION IF EXISTS audit_events_block_mutation();
"""

# Keep the initial migration a stable S0 snapshot. ``target_metadata`` now
# contains post-S0 tables too, so letting this historical migration call
# ``target_metadata.create_all`` directly would make a fresh upgrade create
# rent tables before revision 0002 gets to install their guards.
_S0_TABLES = {
    "users",
    "strategies",
    "strategy_assignments",
    "signals",
    "outbox",
    "order_intents",
    "executions",
    "audit_events",
    "mock_broker_deals",
}


def _s0_metadata() -> MetaData:
    metadata = MetaData(naming_convention=target_metadata.naming_convention)
    for table in target_metadata.sorted_tables:
        if table.name in _S0_TABLES:
            table.to_metadata(metadata)
    return metadata


def upgrade() -> None:
    bind = op.get_bind()
    _s0_metadata().create_all(bind=bind)
    op.execute(_AUDIT_GUARD)


def downgrade() -> None:
    bind = op.get_bind()
    op.execute(_AUDIT_GUARD_DROP)
    target_metadata.drop_all(bind=bind)
