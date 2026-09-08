"""Acceptance 5: an executor timeout produces UNKNOWN + reconciliation, not a
blind retry.

Arms the mock executor's one-shot timeout via Redis, posts a signal, and checks
that the affected execution went through UNKNOWN -> RECONCILED -> FILLED with
reconcile_count >= 1 and exactly one broker deal (no duplicate order).
"""

from __future__ import annotations

import pytest
import redis
from sqlalchemy import text

from conftest import REDIS_URL
from helpers import dev_token, executions_for_signal, poll_until, post_signal, sample_envelope

pytestmark = pytest.mark.integration

ARM_KEY = "mock_exec:arm_timeout"


def test_timeout_goes_unknown_then_reconciles(stack_healthy, engine) -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    r.set(ARM_KEY, "1")

    env = sample_envelope()
    sig_id = env["signal_id"]
    assert post_signal(env).status_code == 202

    admin = dev_token("SUPER_ADMIN")

    def _all_filled() -> bool:
        execs = executions_for_signal(admin, sig_id)
        return len(execs) >= 1 and all(e["state"] == "FILLED" for e in execs)

    poll_until(_all_filled, timeout=60)

    execs = executions_for_signal(admin, sig_id)
    reconciled = [e for e in execs if e["reconcile_count"] >= 1]
    assert reconciled, "expected at least one execution to have been reconciled"

    with engine.connect() as conn:
        # transition audit trail for the reconciled execution
        ex_id = reconciled[0]["id"]
        states = [
            row.data["to"]
            for row in conn.execute(
                text(
                    "SELECT data FROM audit_events WHERE entity_type='execution' "
                    "AND entity_id=:e ORDER BY id"
                ),
                {"e": ex_id},
            )
        ]
        assert "UNKNOWN" in states
        assert "RECONCILED" in states
        assert states[-1] == "FILLED"
        # never re-dispatched after UNKNOWN
        assert "DISPATCHED" not in states[states.index("UNKNOWN") + 1 :]

        # exactly one broker deal per client_order_id => no duplicate order
        dupes = conn.execute(
            text(
                "SELECT client_order_id, count(*) c FROM mock_broker_deals "
                "GROUP BY client_order_id HAVING count(*) > 1"
            )
        ).all()
        assert not dupes

    # cleanup in case the signal only hit some users
    r.delete(ARM_KEY)
