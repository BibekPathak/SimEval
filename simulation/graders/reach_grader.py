"""Automated, deterministic grader for the reach task.

The grader maps recorded episode evidence to a structured :class:`Outcome`, a
primary failure category, the rule that decided the outcome, and a short
explanation grounded in the recorded values.

Design constraints:

* **Deterministic.** Same evidence => same verdict, in any order of evaluation.
* **Task-specific.** Rules are defined per task; the reach grader below only
  applies to the reach task.
* **Testable without a simulator.** The grader consumes a plain
  :class:`GradeInputs` dataclass, so its rules can be unit-tested directly.
* **Reports the deciding rule.** Every verdict names the threshold/rule used.
* **Separates task vs infrastructure failure.** Simulator errors, invalid
  actions, and numerical failures are never attributed to policy quality.

Classification precedence (first match wins):

1. ``SIMULATOR_ERROR``     -- an exception was raised during execution.
2. ``NUMERICAL_FAILURE``   -- non-finite state observed in the recorded trace.
3. ``INVALID_ACTION``      -- the policy produced a non-finite action.
4. ``SUCCESS``             -- the task success condition was met.
5. ``COLLISION``           -- a collision occurred before the target was reached.
6. ``TIMEOUT``             -- the step budget was exhausted.
7. ``TARGET_NOT_REACHED``  -- ended without success, truncation, or collision.
8. ``OTHER_FAILURE``       -- unclassified failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from simulation.runners.outcome import Outcome


@dataclass
class GradeInputs:
    """Evidence consumed by the grader. All values must come from recording."""

    terminated: bool
    truncated: bool
    success: bool
    steps: int
    max_steps: int
    initial_ee_target_dist_m: float
    final_ee_target_dist_m: float
    min_ee_target_dist_m: float
    success_distance_m: float
    collision_steps: int
    max_collision_count: int
    invalid_action: bool = False
    numerical_failure: bool = False
    simulator_error: bool = False
    error_message: str | None = None
    trace_finite: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class GradeResult:
    success: bool
    outcome: Outcome
    failure_category: str | None
    rule: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "outcome": self.outcome.value,
            "failure_category": self.failure_category,
            "rule": self.rule,
            "explanation": self.explanation,
        }


class ReachGrader:
    """Deterministic grader for the reach task."""

    task_name = "reach"

    def grade(self, inputs: GradeInputs) -> GradeResult:
        # 1. Simulator error (infrastructure).
        if inputs.simulator_error:
            msg = inputs.error_message or "unspecified simulator error"
            return GradeResult(
                success=False,
                outcome=Outcome.SIMULATOR_ERROR,
                failure_category=Outcome.SIMULATOR_ERROR.value,
                rule="simulator_error_raised",
                explanation=f"Simulator error raised during execution: {msg}.",
            )

        # 2. Numerical failure (infrastructure).
        if inputs.numerical_failure or not inputs.trace_finite:
            return GradeResult(
                success=False,
                outcome=Outcome.NUMERICAL_FAILURE,
                failure_category=Outcome.NUMERICAL_FAILURE.value,
                rule="non_finite_recorded_state",
                explanation=(
                    "Recorded state contained NaN or Inf during the episode, so the "
                    "outcome cannot be attributed to policy quality."
                ),
            )

        # 3. Invalid action (infrastructure).
        if inputs.invalid_action:
            return GradeResult(
                success=False,
                outcome=Outcome.INVALID_ACTION,
                failure_category=Outcome.INVALID_ACTION.value,
                rule="non_finite_action_emitted",
                explanation=(
                    "The policy emitted a non-finite action. This is an action-interface "
                    "failure, not a task-performance result."
                ),
            )

        # 4. Success (task).
        if inputs.success and inputs.terminated:
            return GradeResult(
                success=True,
                outcome=Outcome.SUCCESS,
                failure_category=None,
                rule=f"final_dist < {inputs.success_distance_m} m (dwell satisfied)",
                explanation=(
                    f"End effector held within {inputs.success_distance_m} m of the target "
                    f"(final distance {inputs.final_ee_target_dist_m:.4f} m, "
                    f"min {inputs.min_ee_target_dist_m:.4f} m)."
                ),
            )

        # 5. Collision before reaching the target (task failure).
        if inputs.collision_steps > 0 and not inputs.success:
            return GradeResult(
                success=False,
                outcome=Outcome.COLLISION,
                failure_category=Outcome.COLLISION.value,
                rule="collision_steps > 0 and not success",
                explanation=(
                    f"End effector contacted the floor on {inputs.collision_steps} "
                    f"recorded step(s) (max {inputs.max_collision_count} simultaneous "
                    f"contacts) and never satisfied the success condition."
                ),
            )

        # 6. Timeout (task failure: did not reach target within the budget).
        if inputs.truncated:
            return GradeResult(
                success=False,
                outcome=Outcome.TIMEOUT,
                failure_category=Outcome.TIMEOUT.value,
                rule=f"steps >= max_steps ({inputs.max_steps}) without success",
                explanation=(
                    f"Episode used the full {inputs.steps}-step budget without success; "
                    f"closest approach was {inputs.min_ee_target_dist_m:.4f} m "
                    f"(threshold {inputs.success_distance_m} m)."
                ),
            )

        # 7. Target not reached (task failure: ended early, no success, no timeout).
        if not inputs.success:
            return GradeResult(
                success=False,
                outcome=Outcome.TARGET_NOT_REACHED,
                failure_category=Outcome.TARGET_NOT_REACHED.value,
                rule="episode ended without success, truncation, or collision",
                explanation=(
                    f"Episode ended after {inputs.steps} step(s) without reaching the "
                    f"target; closest approach was {inputs.min_ee_target_dist_m:.4f} m "
                    f"(threshold {inputs.success_distance_m} m)."
                ),
            )

        # 8. Unclassified.
        return GradeResult(
            success=False,
            outcome=Outcome.OTHER_FAILURE,
            failure_category=Outcome.OTHER_FAILURE.value,
            rule="no classification rule matched",
            explanation="Episode did not match any defined success or failure rule.",
        )


#: Registry of graders by task name. Extend when new tasks are added.
GRADERS: dict[str, ReachGrader] = {"reach": ReachGrader()}


def get_grader(task_name: str) -> ReachGrader:
    if task_name not in GRADERS:
        raise KeyError(f"no grader registered for task '{task_name}'")
    return GRADERS[task_name]


__all__ = ["GRADERS", "GradeInputs", "GradeResult", "ReachGrader", "get_grader"]
