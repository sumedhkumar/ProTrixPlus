"""mt5_connections.metaapi_account_id / metaapi_region

Revision ID: 0005_mt5_connection_metaapi
Revises: 0004_strategy_symbol
Create Date: 2026-09-20

ADR-001's MetaApiExecutionAdapter needs a per-client MetaApi trading account
id to route real orders to the right broker account, plus the MetaApi region
that account was provisioned in (required to build the correct regional API
host - see worker/app/adapters/metaapi.py). Both nullable: a connection can
exist (broker_server/login only) before an admin has attached the MetaApi
side of it. Still never stores a password - see the model's docstring.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_mt5_connection_metaapi"
down_revision: str | None = "0004_strategy_symbol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mt5_connections", sa.Column("metaapi_account_id", sa.String(64), nullable=True)
    )
    op.add_column("mt5_connections", sa.Column("metaapi_region", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("mt5_connections", "metaapi_region")
    op.drop_column("mt5_connections", "metaapi_account_id")
