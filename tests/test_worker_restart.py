"""Acceptance 4: killing + restarting the worker after the signal is persisted
loses nothing and duplicates nothing.

Strategy: pause the worker, post a signal (api persists it + an outbox row),
restart the worker. Its startup catch-up sweep + the outbox relay + idempotent
fan-out must converge to exactly one intent/execution per user.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from sqlalchemy import text

from conftest import COMPOSE_FILE
from helpers import dev_token, executions_for_signal, poll_until, post_signal, sample_envelope

pytestmark = [pytest.mark.integration, pytest.mark.needs_docker]


def _compose(*args: str) -> None:
    project = os.environ.get("PROTRIX_COMPOSE_PROJECT")
    command = ["docker", "compose"]
    if project:
        command.extend(["-p", project])
    command.extend(["-f", COMPOSE_FILE, *args])
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture(autouse=True)
def _require_docker() -> None:
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available")


def test_restart_loses_nothing_and_duplicates_nothing(stack_healthy, engine) -> None:
    # 1. Stop the worker so nothing consumes while we post.
    _compose("stop", "worker")

    env = sample_envelope()
    sig_id = env["signal_id"]
    resp = post_signal(env)
    assert resp.status_code == 202

    # 2. Signal is durably persisted even though the worker is down.
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM signals WHERE signal_id = :s"), {"s": sig_id}
            ).scalar_one()
            == 1
        )
        pending = conn.execute(
            text("SELECT count(*) FROM outbox WHERE status = 'PENDING'")
        ).scalar_one()
        assert pending >= 1

    # 3. Bring the worker back.
    _compose("start", "worker")

    admin = dev_token("SUPER_ADMIN")

    def _all_filled() -> bool:
        execs = executions_for_signal(admin, sig_id)
        return len(execs) >= 1 and all(e["state"] == "FILLED" for e in execs)

    poll_until(_all_filled, timeout=90)

    with engine.connect() as conn:
        n_users = int(
            conn.execute(text("SELECT count(*) FROM users WHERE role='USER'")).scalar_one()
        )
        intents = conn.execute(
            text(
                "SELECT count(*) FROM order_intents oi JOIN signals s ON s.id=oi.signal_id "
                "WHERE s.signal_id=:s"
            ),
            {"s": sig_id},
        ).scalar_one()
        execs = conn.execute(
            text(
                "SELECT count(*) FROM executions e "
                "JOIN order_intents oi ON oi.id=e.order_intent_id "
                "JOIN signals s ON s.id=oi.signal_id WHERE s.signal_id=:s"
            ),
            {"s": sig_id},
        ).scalar_one()

    assert intents == n_users, "restart duplicated or dropped an intent"
    assert execs == n_users, "restart duplicated or dropped an execution"
