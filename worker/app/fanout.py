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

from protrix_contracts.db.models import (
    AuditEvent,
    Execution,
    ManagedPosition,
    ManagedPositionStatus,
    OrderIntent,
    Signal,
    Strategy,
    StrategyAssignment,
    User,
)
from protrix_contracts.envelope import command_target_for_action
from protrix_contracts.lifecycle import ExecutionState
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.adapters.base import ExecutionAdapter
from app.eligibility import Eligibility, entry_risk_reasons, evaluate
from app.execution import drive_new_execution, reconcile_unknown
from app.sizing import compute_lot

log = logging.getLogger("worker.fanout")

_INTENT_UNIQUE = "uq_order_intents_signal_op_key"


def _upsert_intent(
    session: Session,
    *,
    user: User,
    strategy: Strategy,
    signal: Signal,
    command_target: str,
    execution_key: str,
    action: str,
    lot: object,
    assignment: StrategyAssignment,
    eligibility_status: str,
) -> OrderIntent:
    session.execute(
        pg_insert(OrderIntent)
        .values(
            user_id=user.id,
            strategy_id=strategy.id,
            signal_id=signal.id,
            command_target=command_target,
            execution_key=execution_key,
            action=action,
            symbol=signal.symbol,
            computed_lot=lot,
            master_lot=assignment.master_lot,
            multiplier=assignment.multiplier,
            eligibility_status=eligibility_status,
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
            OrderIntent.execution_key == execution_key,
        )
    )
    assert intent is not None  # noqa: S101 - just upserted or pre-existing
    return intent


def _ensure_execution(
    session: Session,
    intent: OrderIntent,
    adapter: ExecutionAdapter,
    touched: list[Execution],
) -> Execution:
    execution = session.scalar(select(Execution).where(Execution.order_intent_id == intent.id))
    if execution is None:
        execution = drive_new_execution(session, intent, adapter)
        touched.append(execution)
    elif execution.state == ExecutionState.UNKNOWN.value:
        reconcile_unknown(session, execution, adapter)
        touched.append(execution)
    else:
        log.debug("intent %s already has execution in %s", intent.id, execution.state)
    return execution


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
    if strategy is None or not strategy.is_active:
        log.warning(
            "process_signal: strategy %s/%s missing or inactive",
            signal.strategy_key,
            signal.strategy_version,
        )
        return []

    command_target = command_target_for_action(signal.action).value

    is_entry_signal = command_target == "ENTRY"
    assignment_query = (
        select(StrategyAssignment, User)
        .join(User, StrategyAssignment.user_id == User.id)
        .where(
            StrategyAssignment.strategy_id == strategy.id,
            User.is_active.is_(True),
        )
    )
    if is_entry_signal:
        assignment_query = assignment_query.where(StrategyAssignment.status == "ACTIVE")
    if active_user_email:
        assignment_query = assignment_query.where(User.email == active_user_email)
    pairs = session.execute(assignment_query.order_by(User.created_at)).all()

    touched: list[Execution] = []
    for assignment, user in pairs:
        decision = evaluate(session, user, assignment)
        if is_entry_signal and decision.status is not Eligibility.ACTIVE:
            log.info("skip user=%s: entry eligibility=%s", user.id, decision.status.value)
            continue

        lot = compute_lot(
            master_lot=assignment.master_lot,
            multiplier=assignment.multiplier,
            multiplier_min=assignment.multiplier_min,
            multiplier_max=assignment.multiplier_max,
        )
        if is_entry_signal:
            direction = signal.action.upper()
            open_positions = session.scalars(
                select(ManagedPosition).where(
                    ManagedPosition.user_id == user.id,
                    ManagedPosition.strategy_id == strategy.id,
                    ManagedPosition.symbol == signal.symbol,
                    ManagedPosition.status == ManagedPositionStatus.OPEN.value,
                )
            ).all()
            opposite_positions = [
                position for position in open_positions if position.side != direction
            ]
            same_direction_exists = any(position.side == direction for position in open_positions)

            # Directional TradingView alerts carry no explicit exit. A reversal
            # therefore closes only server-tracked opposite positions before
            # the new entry. Never use a broker ticket from the webhook.
            close_failed = False
            for position in opposite_positions:
                close_intent = _upsert_intent(
                    session,
                    user=user,
                    strategy=strategy,
                    signal=signal,
                    command_target="CLOSE",
                    execution_key=position.source_position_ref,
                    action="CLOSE",
                    lot=lot,
                    assignment=assignment,
                    eligibility_status=decision.status.value,
                )
                close_execution = _ensure_execution(session, close_intent, adapter, touched)
                if close_execution.state != ExecutionState.FILLED.value:
                    close_failed = True
                    log.error(
                        "reverse signal %s did not close managed position %s; entry withheld",
                        signal.signal_id,
                        position.id,
                    )
                    break
            if close_failed:
                session.commit()
                continue

            if same_direction_exists:
                session.add(
                    AuditEvent(
                        event_type="entry.skipped_same_direction",
                        entity_type="signal",
                        entity_id=str(signal.id),
                        actor="worker",
                        data={"user_id": str(user.id), "direction": direction},
                    )
                )
                session.commit()
                continue

            # Check position-count risk only after a successful reversal close.
            risk_reasons = entry_risk_reasons(
                session, user_id=user.id, symbol=signal.symbol, volume=lot
            )
            if risk_reasons:
                session.add(
                    AuditEvent(
                        event_type="entry.risk_blocked",
                        entity_type="signal",
                        entity_id=str(signal.id),
                        actor="worker",
                        data={"user_id": str(user.id), "reasons": list(risk_reasons)},
                    )
                )
                session.commit()
                continue
            intent = _upsert_intent(
                session,
                user=user,
                strategy=strategy,
                signal=signal,
                command_target="ENTRY",
                execution_key="entry",
                action=signal.action,
                lot=lot,
                assignment=assignment,
                eligibility_status=decision.status.value,
            )
        else:
            # Explicit management signals still resolve their source reference
            # through the managed-position table in execution._dto.
            intent = _upsert_intent(
                session,
                user=user,
                strategy=strategy,
                signal=signal,
                command_target=command_target,
                execution_key=signal.position_ref or "missing-position-ref",
                action=signal.action,
                lot=lot,
                assignment=assignment,
                eligibility_status=decision.status.value,
            )

        _ensure_execution(session, intent, adapter, touched)

        # Commit per user so an interrupt here loses nothing already done.
        session.commit()

    log.info(
        "signal %s fanned out: %d eligible pair(s), %d execution(s) touched",
        signal.signal_id,
        len(pairs),
        len(touched),
    )
    return touched
