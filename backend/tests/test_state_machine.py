"""Tests for the experiment state machine (no DB, no simulator)."""

from __future__ import annotations

import pytest

from backend.app.services.state_machine import (
    ExperimentStatus,
    InvalidTransition,
    assert_transition,
    can_transition,
    coerce,
    is_terminal,
)


def test_happy_path_transitions() -> None:
    assert_transition(ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)
    assert_transition(ExperimentStatus.RUNNING, ExperimentStatus.COMPLETED)


def test_terminal_states_have_no_exit() -> None:
    for terminal in (
        ExperimentStatus.COMPLETED,
        ExperimentStatus.FAILED,
        ExperimentStatus.CANCELLED,
    ):
        assert is_terminal(terminal)
        for dst in ExperimentStatus:
            assert not can_transition(terminal, dst)


def test_cannot_complete_from_queued() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(ExperimentStatus.QUEUED, ExperimentStatus.COMPLETED)


def test_queued_can_cancel() -> None:
    assert_transition(ExperimentStatus.QUEUED, ExperimentStatus.CANCELLED)


def test_running_can_requeue_after_restart() -> None:
    assert_transition(ExperimentStatus.RUNNING, ExperimentStatus.QUEUED)


def test_cancel_completed_raises() -> None:
    with pytest.raises(InvalidTransition):
        assert_transition(ExperimentStatus.COMPLETED, ExperimentStatus.CANCELLED)


def test_coerce_invalid() -> None:
    assert coerce("RUNNING") == ExperimentStatus.RUNNING
    with pytest.raises(ValueError):
        coerce("NOPE")
