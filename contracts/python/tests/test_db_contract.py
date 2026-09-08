"""The DB contract: constraint names other services rely on, and JSONB safety."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from protrix_contracts.db import metadata
from protrix_contracts.db.session import _json_serializer


def _constraint_names() -> set[str]:
    names: set[str] = set()
    for table in metadata.tables.values():
        for c in table.constraints:
            if c.name:
                names.add(str(c.name))
        for idx in table.indexes:
            if idx.name:
                names.add(str(idx.name))
    return names


def test_invariant_constraints_exist_by_name() -> None:
    names = _constraint_names()
    # no-duplicate-intent (fan-out inserts ON CONFLICT against this exact name)
    assert "uq_order_intents_user_id_strategy_id_signal_id_command_target" in names
    # idempotent acceptance
    assert "uq_signals_signal_id" in names
    assert "uq_signals_idempotency_key" in names
    # one execution per intent
    assert "uq_executions_order_intent_id" in names
    assert "uq_executions_client_order_id" in names


def test_all_tables_compile_for_postgres() -> None:
    dialect = postgresql.dialect()
    for table in metadata.sorted_tables:
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=dialect))


def test_expected_tables_present() -> None:
    assert {
        "users",
        "strategies",
        "strategy_assignments",
        "signals",
        "outbox",
        "order_intents",
        "executions",
        "audit_events",
        "mock_broker_deals",
    } <= set(metadata.tables)


def test_jsonb_serializer_rejects_float_but_accepts_decimal() -> None:
    assert _json_serializer({"lot": Decimal("1.50")}) == '{"lot":"1.50"}'
