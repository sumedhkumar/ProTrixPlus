"""Acceptance 2: the mock signal slice runs end to end and the dashboards show
stored signal + execution status.

Also traces the 'durable before acknowledge' invariant: the signal row is
readable over a fresh DB connection the instant the webhook returns 2xx.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from conftest import count
from helpers import (
    api_get,
    dev_token,
    executions_for_signal,
    poll_until,
    post_signal,
    sample_envelope,
)

pytestmark = pytest.mark.integration


def test_full_slice(stack_healthy, engine) -> None:
    env = sample_envelope()
    sig_id = env["signal_id"]

    resp = post_signal(env)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["accepted"] is True and body["duplicate"] is False
    assert body["payload_hash"].startswith("sha256:")

    # Durable before acknowledge: visible on a brand-new connection right now.
    with engine.connect() as fresh:
        row = fresh.execute(
            text("SELECT accepted_at, payload_hash FROM signals WHERE signal_id = :s"),
            {"s": sig_id},
        ).first()
        assert row is not None, "signal not persisted before 2xx"
        assert row.payload_hash == body["payload_hash"]

    user = dev_token("USER")
    admin = dev_token("SUPER_ADMIN")

    # Signal shows up on the dashboards' read API.
    poll_until(
        lambda: any(s["signal_id"] == sig_id for s in api_get("/api/v1/signals", user)),
        timeout=15,
    )

    # Worker fan-out -> mock executor -> stored execution reaches FILLED.
    def _filled() -> bool:
        execs = executions_for_signal(admin, sig_id)
        return len(execs) >= 1 and all(e["state"] == "FILLED" for e in execs)

    poll_until(_filled, timeout=45)

    execs = executions_for_signal(admin, sig_id)
    # one intent + one execution per seeded USER
    with engine.connect() as conn:
        n_users = int(
            conn.execute(text("SELECT count(*) FROM users WHERE role = 'USER'")).scalar_one()
        )
        assert count(conn, "order_intents") >= n_users
    assert len(execs) == n_users
    for e in execs:
        assert e["ticket_id"] and e["deal_id"]
        assert e["adapter"] == "mock"
        assert e["latency_fill_ms"] is not None
