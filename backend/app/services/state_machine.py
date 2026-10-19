"""Experiment lifecycle state machine.

States: ``QUEUED -> RUNNING -> COMPLETED`` with ``FAILED`` and ``CANCELLED`` as
terminal alternatives. Invalid transitions raise, so the API and worker cannot
corrupt state.
"""

from __future__ import annotations

from enum import StrEnum


class ExperimentStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL: frozenset[ExperimentStatus] = frozenset(
    {ExperimentStatus.COMPLETED, ExperimentStatus.FAILED, ExperimentStatus.CANCELLED}
)

#: Allowed transitions. A state maps to the set of states it may move to.
_TRANSITIONS: dict[ExperimentStatus, frozenset[ExperimentStatus]] = {
    ExperimentStatus.QUEUED: frozenset(
        {ExperimentStatus.RUNNING, ExperimentStatus.CANCELLED, ExperimentStatus.FAILED}
    ),
    ExperimentStatus.RUNNING: frozenset(
        {
            ExperimentStatus.COMPLETED,
            ExperimentStatus.FAILED,
            ExperimentStatus.CANCELLED,
            ExperimentStatus.QUEUED,  # requeue after worker restart
        }
    ),
    ExperimentStatus.COMPLETED: frozenset(),
    ExperimentStatus.FAILED: frozenset(),
    ExperimentStatus.CANCELLED: frozenset(),
}


class InvalidTransition(RuntimeError):
    def __init__(self, src: ExperimentStatus, dst: ExperimentStatus) -> None:
        super().__init__(f"invalid experiment transition {src.value} -> {dst.value}")
        self.src = src
        self.dst = dst


def can_transition(src: ExperimentStatus, dst: ExperimentStatus) -> bool:
    return dst in _TRANSITIONS[src]


def assert_transition(src: ExperimentStatus, dst: ExperimentStatus) -> None:
    if not can_transition(src, dst):
        raise InvalidTransition(src, dst)


def is_terminal(status: ExperimentStatus) -> bool:
    return status in TERMINAL


def coerce(status: str) -> ExperimentStatus:
    return ExperimentStatus(status)


__all__ = [
    "TERMINAL",
    "ExperimentStatus",
    "InvalidTransition",
    "assert_transition",
    "can_transition",
    "coerce",
    "is_terminal",
]
