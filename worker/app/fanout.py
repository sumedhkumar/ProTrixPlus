"""Signal fan-out: one signal -> one order intent per eligible (user, strategy,
signal, command_target) -> one execution per intent.

Every step is idempotent and resumable:

* the intent insert is ``ON CONFLICT DO NOTHING`` against the DB unique
  constraint, so a replayed signal creates no second intent;
* an execution is only started for an intent that has none yet;
* an intent whose execution is stuck in UNKNOWN is reconciled, never re-sent.

That is what makes the worker-restart and duplicate-signal tests pass.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from protrix_contracts.db.models import (
    Execution,
    OrderIntent,
    Signal,
    Strategy,
    StrategyAssignment,
    User,
)
from protrix_contracts.envelope import MANAGEMENT_ACTIONS, Action, command_target_for_action
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.adapters.base import ExecutionAdapter
from app.eligibility import Eligibility, evaluate
from app.execution import drive_new_execution, reconcile_unknown
from app.sizing import compute_lot

log = logging.getLogger("worker.fanout")

_INTENT_UNIQUE = "uq_order_intents_user_id_strategy_id_signal_id_command_target"


def process_signal(
    session: Session,
    signal_row_id: str | uuid.UUID,
    adapter: ExecutionAdapter,
    *,
    active_user_email: str | None = None,
) -> list[Execution]:
    signal = session.get(Signal, uuid.UUID(str(signal_row_id)))
    if signal is None:
        log.warning("process_signal: no signal row %s", signal_row_id)
        return []

    strategy = session.scalar(
        select(Strategy).where(
            Strategy.strategy_key == signal.strategy_key,
            Strategy.strategy_version == signal.strategy_version,
        )
    )
    if strategy is None:
        log.warning(
            "process_signal: strategy %s/%s missing", signal.strategy_key, signal.strategy_version
        )
        return []

    # PRD 4.3 step 5 / docs/FULL-BUILD-PLAN.md decision #3: OFF blocks NEW
    # entries only. A management/exit action (CLOSE, PARTIAL_CLOSE,
    # MODIFY_SLTP, EMERGENCY_CLOSE) must still be able to close an already-open
    # position even while the strategy is OFF - otherwise turning a strategy
    # off would strand every client's open position with no way to exit it.
    is_management = Action(signal.action) in MANAGEMENT_ACTIONS
    if not strategy.is_active and not is_management:
        log.info(
            "process_signal: strategy %s/%s is OFF, blocking new entry",
            signal.strategy_key,
            signal.strategy_version,
        )
        return []

    command_target = command_target_for_action(signal.action).value

    assignment_query = (
        select(StrategyAssignment, User)
        .join(User, StrategyAssignment.user_id == User.id)
        .where(
            StrategyAssignment.strategy_id == strategy.id,
            StrategyAssignment.status == "ACTIVE",
            User.is_active.is_(True),
        )
    )
    if active_user_email:
        assignment_query = assignment_query.where(User.email == active_user_email)
    pairs = session.execute(assignment_query.order_by(User.created_at)).all()

    touched: list[Execution] = []
    now = datetime.now(UTC)
    for assignment, user in pairs:
        decision = evaluate(user, assignment, now=now)
        if decision.status is not Eligibility.ACTIVE:
            log.info("skip user=%s: eligibility=%s", user.id, decision.status.value)
            continue

        lot = compute_lot(
            master_lot=assignment.master_lot,
            multiplier=assignment.multiplier,
            multiplier_min=assignment.multiplier_min,
            multiplier_max=assignment.multiplier_max,
        )

        session.execute(
            pg_insert(OrderIntent)
            .values(
                user_id=user.id,
                strategy_id=strategy.id,
                signal_id=signal.id,
                command_target=command_target,
                action=signal.action,
                symbol=signal.symbol,
                computed_lot=lot,
                master_lot=assignment.master_lot,
                multiplier=assignment.multiplier,
                eligibility_status=decision.status.value,
                status="CREATED",
            )
            .on_conflict_do_nothing(constraint=_INTENT_UNIQUE)
        )

        intent = session.scalar(
            select(OrderIntent).where(
                OrderIntent.user_id == user.id,
                OrderIntent.strategy_id == strategy.id,
                OrderIntent.signal_id == signal.id,
                OrderIntent.command_target == command_target,
            )
        )
        assert intent is not None  # noqa: S101 - just upserted or pre-existing

        execution = session.scalar(select(Execution).where(Execution.order_intent_id == intent.id))
        if execution is None:
            execution = drive_new_execution(session, intent, adapter)
            touched.append(execution)
        elif execution.state == ExecutionState.UNKNOWN.value:
            reconcile_unknown(session, execution, adapter)
            touched.append(execution)
        else:
            log.debug("intent %s already has execution in %s", intent.id, execution.state)

        # Commit per user so an interrupt here loses nothing already done.
        session.commit()

    log.info(
        "signal %s fanned out: %d eligible pair(s), %d execution(s) touched",
        signal.signal_id,
        len(pairs),
        len(touched),
    )
    return touched
