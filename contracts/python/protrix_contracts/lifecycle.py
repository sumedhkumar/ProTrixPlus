"""Execution lifecycle state machine.

Minimal now, but the full shape is declared so later steps only add edges, never
rename states. Backward / arbitrary edits are rejected by
:func:`assert_transition`.

Happy path exercised by S0::

    RECEIVED -> INTENT_CREATED -> QUEUED -> DISPATCHED -> ACKNOWLEDGED -> FILLED

Timeout path::

    DISPATCHED -> UNKNOWN -> RECONCILED -> (FILLED | REJECTED)

``UNKNOWN`` is explicitly *not* a failure: it means "we do not know", and the
only edge out of it goes through reconciliation. There is no edge that re-sends
an order.
"""

from __future__ import annotations

import enum


class ExecutionState(str, enum.Enum):
    RECEIVED = "RECEIVED"
    INTENT_CREATED = "INTENT_CREATED"
    QUEUED = "QUEUED"
    DISPATCHED = "DISPATCHED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


TERMINAL_STATES: frozenset[ExecutionState] = frozenset(
    {ExecutionState.FILLED, ExecutionState.REJECTED}
)

# Directed edges. Anything not listed here is forbidden.
_ALLOWED: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.RECEIVED: frozenset({ExecutionState.INTENT_CREATED, ExecutionState.REJECTED}),
    ExecutionState.INTENT_CREATED: frozenset({ExecutionState.QUEUED, ExecutionState.REJECTED}),
    ExecutionState.QUEUED: frozenset({ExecutionState.DISPATCHED, ExecutionState.REJECTED}),
    ExecutionState.DISPATCHED: frozenset(
        {
            ExecutionState.ACKNOWLEDGED,
            ExecutionState.REJECTED,
            ExecutionState.UNKNOWN,
        }
    ),
    ExecutionState.ACKNOWLEDGED: frozenset(
        {ExecutionState.FILLED, ExecutionState.REJECTED, ExecutionState.UNKNOWN}
    ),
    ExecutionState.UNKNOWN: frozenset({ExecutionState.RECONCILED}),
    ExecutionState.RECONCILED: frozenset({ExecutionState.FILLED, ExecutionState.REJECTED}),
    ExecutionState.FILLED: frozenset(),
    ExecutionState.REJECTED: frozenset(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, src: ExecutionState, dst: ExecutionState) -> None:
        self.src = src
        self.dst = dst
        super().__init__(f"illegal execution transition {src.value} -> {dst.value}")


def can_transition(src: ExecutionState | str, dst: ExecutionState | str) -> bool:
    src_s, dst_s = ExecutionState(src), ExecutionState(dst)
    return dst_s in _ALLOWED[src_s]


def assert_transition(src: ExecutionState | str, dst: ExecutionState | str) -> ExecutionState:
    src_s, dst_s = ExecutionState(src), ExecutionState(dst)
    if dst_s not in _ALLOWED[src_s]:
        raise InvalidTransitionError(src_s, dst_s)
    return dst_s


def allowed_next(src: ExecutionState | str) -> frozenset[ExecutionState]:
    return _ALLOWED[ExecutionState(src)]
