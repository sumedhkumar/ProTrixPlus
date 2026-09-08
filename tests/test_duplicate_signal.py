"""Acceptance 3: duplicate sample signals create no second signal / intent /
execution row."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from helpers import dev_token, executions_for_signal, poll_until, post_signal, sample_envelope

pytestmark = pytest.mark.integration


def _counts(conn, signal_ref: str) -> tuple[int, int, int]:
    sig = conn.execute(
        text("SELECT count(*) FROM signals WHERE signal_id = :s"), {"s": signal_ref}
    ).scalar_one()
    intents = conn.execute(
        text(
            "SELECT count(*) FROM order_intents oi "
            "JOIN signals s ON s.id = oi.signal_id WHERE s.signal_id = :s"
        ),
        {"s": signal_ref},
    ).scalar_one()
    execs = conn.execute(
        text(
            "SELECT count(*) FROM executions e "
            "JOIN order_intents oi ON oi.id = e.order_intent_id "
            "JOIN signals s ON s.id = oi.signal_id WHERE s.signal_id = :s"
        ),
        {"s": signal_ref},
    ).scalar_one()
    return int(sig), int(intents), int(execs)


def test_duplicate_creates_nothing_new(stack_healthy, engine) -> None:
    env = sample_envelope()
    sig_id = env["signal_id"]

    first = post_signal(env)
    assert first.status_code == 202
    assert first.json()["duplicate"] is False

    admin = dev_token("SUPER_ADMIN")
    poll_until(
        lambda: len(executions_for_signal(admin, sig_id)) >= 1
        and all(e["state"] == "FILLED" for e in executions_for_signal(admin, sig_id)),
        timeout=45,
    )

    with engine.connect() as conn:
        before = _counts(conn, sig_id)

    # Re-post the exact same envelope twice more.
    for _ in range(2):
        dup = post_signal(env)
        assert dup.status_code == 200, dup.text
        assert dup.json()["duplicate"] is True

    # Give the worker a chance to (not) do anything.
    import time

    time.sleep(3)

    with engine.connect() as conn:
        after = _counts(conn, sig_id)

    assert after == before, f"duplicate signal changed row counts: {before} -> {after}"
    assert before[0] == 1  # exactly one signal row
