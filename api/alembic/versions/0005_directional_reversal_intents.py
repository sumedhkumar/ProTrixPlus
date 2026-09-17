"""allow one directional reversal signal to close each tracked position"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "0005_directional_reversal"
down_revision: str | None = "0004_mvp_controls_and_positions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_UNIQUE = "uq_order_intents_user_id_strategy_id_signal_id_command_target"
_NEW_UNIQUE = "uq_order_intents_signal_op_key"


def upgrade() -> None:
    if context.is_offline_mode():
        # Offline SQL has no inspector. The S0 snapshot is exact, so these
        # operations are known to be required on a clean upgrade.
        op.add_column(
            "order_intents",
            sa.Column("execution_key", sa.String(length=128), nullable=True),
        )
        op.execute("UPDATE order_intents SET execution_key = 'entry' WHERE execution_key IS NULL")
        op.alter_column("order_intents", "execution_key", nullable=False)
        op.drop_constraint(_OLD_UNIQUE, "order_intents", type_="unique")
        op.create_unique_constraint(
            _NEW_UNIQUE,
            "order_intents",
            ["user_id", "strategy_id", "signal_id", "command_target", "execution_key"],
        )
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("order_intents")}
    if "execution_key" not in columns:
        op.add_column(
            "order_intents",
            sa.Column("execution_key", sa.String(length=128), nullable=True),
        )
        op.execute("UPDATE order_intents SET execution_key = 'entry' WHERE execution_key IS NULL")
        op.alter_column("order_intents", "execution_key", nullable=False)

    constraints = {item["name"] for item in inspector.get_unique_constraints("order_intents")}
    if _OLD_UNIQUE in constraints:
        op.drop_constraint(_OLD_UNIQUE, "order_intents", type_="unique")
    if _NEW_UNIQUE not in constraints:
        op.create_unique_constraint(
            _NEW_UNIQUE,
            "order_intents",
            ["user_id", "strategy_id", "signal_id", "command_target", "execution_key"],
        )


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_constraint(_NEW_UNIQUE, "order_intents", type_="unique")
        op.create_unique_constraint(
            _OLD_UNIQUE,
            "order_intents",
            ["user_id", "strategy_id", "signal_id", "command_target"],
        )
        op.drop_column("order_intents", "execution_key")
        return
    bind = op.get_bind()
    constraints = {
        item["name"] for item in sa.inspect(bind).get_unique_constraints("order_intents")
    }
    if _NEW_UNIQUE in constraints:
        op.drop_constraint(_NEW_UNIQUE, "order_intents", type_="unique")
    if _OLD_UNIQUE not in constraints:
        op.create_unique_constraint(
            _OLD_UNIQUE,
            "order_intents",
            ["user_id", "strategy_id", "signal_id", "command_target"],
        )
    columns = {column["name"] for column in sa.inspect(bind).get_columns("order_intents")}
    if "execution_key" in columns:
        op.drop_column("order_intents", "execution_key")
