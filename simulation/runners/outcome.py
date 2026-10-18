"""Shared episode outcome types for the runner, grader, and metrics.

Failure categories separate *task* failures (the policy did not accomplish the
objective) from *infrastructure* failures (the simulator or plumbing failed).
An infrastructure failure must never be counted as evidence that a policy is
bad, so the two are distinct enum values with an explicit classifier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np


class Outcome(StrEnum):
    """Structured episode outcome assigned by the grader."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    TARGET_NOT_REACHED = "TARGET_NOT_REACHED"
    COLLISION = "COLLISION"
    INVALID_ACTION = "INVALID_ACTION"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"
    SIMULATOR_ERROR = "SIMULATOR_ERROR"
    OTHER_FAILURE = "OTHER_FAILURE"


#: Categories that indicate the evaluation infrastructure failed rather than the
#: policy. These must be excluded from policy-quality claims.
INFRASTRUCTURE_OUTCOMES: frozenset[Outcome] = frozenset(
    {Outcome.SIMULATOR_ERROR, Outcome.INVALID_ACTION, Outcome.NUMERICAL_FAILURE}
)


def is_infrastructure_failure(outcome: Outcome) -> bool:
    return outcome in INFRASTRUCTURE_OUTCOMES


@dataclass
class EpisodeResult:
    """The complete, persisted record of a single episode execution."""

    episode_id: str
    experiment_id: str
    scenario_id: str
    policy_name: str
    policy_version: str
    task_name: str
    task_version: str
    seed: int
    split: str
    difficulty: str
    success: bool
    outcome: str  # Outcome value (kept as str for serialization)
    failure_category: str | None
    explanation: str
    rule: str
    steps: int
    wall_clock_s: float
    sim_time_s: float
    return_sum: float
    min_ee_target_dist_m: float
    final_ee_target_dist_m: float
    initial_ee_target_dist_m: float
    collision_steps: int
    max_collision_count: int
    policy_inference_s: float
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_ref: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        import dataclasses

        return dataclasses.asdict(self)


def finite_float(value: Any, default: float | None = None) -> float | None:
    """Return a finite float or ``default`` — guards against NaN/Inf leakage."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(f):
        return default
    return f


__all__ = [
    "INFRASTRUCTURE_OUTCOMES",
    "EpisodeResult",
    "Outcome",
    "finite_float",
    "is_infrastructure_failure",
]
