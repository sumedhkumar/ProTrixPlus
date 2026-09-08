"""Unit: execution transition validator."""

from __future__ import annotations

import pytest

from protrix_contracts.lifecycle import (
    ExecutionState,
    InvalidTransitionError,
    allowed_next,
    assert_transition,
    can_transition,
)

HAPPY_PATH = [
    ExecutionState.RECEIVED,
    ExecutionState.INTENT_CREATED,
    ExecutionState.QUEUED,
    ExecutionState.DISPATCHED,
    ExecutionState.ACKNOWLEDGED,
    ExecutionState.FILLED,
]

TIMEOUT_PATH = [
    ExecutionState.DISPATCHED,
    ExecutionState.UNKNOWN,
    ExecutionState.RECONCILED,
    ExecutionState.FILLED,
]


@pytest.mark.parametrize("path", [HAPPY_PATH, TIMEOUT_PATH], ids=["happy", "timeout"])
def test_valid_paths(path) -> None:
    for src, dst in zip(path, path[1:], strict=False):
        assert can_transition(src, dst)
        assert assert_transition(src, dst) is dst


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (ExecutionState.FILLED, ExecutionState.DISPATCHED),  # backward
        (ExecutionState.ACKNOWLEDGED, ExecutionState.RECEIVED),  # backward
        (ExecutionState.QUEUED, ExecutionState.FILLED),  # skip
        (ExecutionState.UNKNOWN, ExecutionState.FILLED),  # must reconcile first
        (ExecutionState.REJECTED, ExecutionState.RECONCILED),  # terminal
        (ExecutionState.UNKNOWN, ExecutionState.DISPATCHED),  # never re-send
    ],
)
def test_illegal_transitions_raise(src, dst) -> None:
    assert not can_transition(src, dst)
    with pytest.raises(InvalidTransitionError):
        assert_transition(src, dst)


def test_unknown_only_leads_to_reconciled() -> None:
    assert allowed_next(ExecutionState.UNKNOWN) == frozenset({ExecutionState.RECONCILED})


def test_terminal_states_have_no_exits() -> None:
    assert allowed_next(ExecutionState.FILLED) == frozenset()
    assert allowed_next(ExecutionState.REJECTED) == frozenset()
