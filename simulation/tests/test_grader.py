"""Tests for the reach grader. These do not require the simulator."""

from __future__ import annotations

import pytest

from simulation.graders.reach_grader import GradeInputs, ReachGrader, get_grader
from simulation.runners.outcome import Outcome, is_infrastructure_failure


@pytest.fixture()
def grader() -> ReachGrader:
    return ReachGrader()


def _inputs(**overrides: object) -> GradeInputs:
    base: dict[str, object] = {
        "terminated": True,
        "truncated": False,
        "success": True,
        "steps": 50,
        "max_steps": 400,
        "initial_ee_target_dist_m": 0.3,
        "final_ee_target_dist_m": 0.03,
        "min_ee_target_dist_m": 0.03,
        "success_distance_m": 0.05,
        "collision_steps": 0,
        "max_collision_count": 0,
    }
    base.update(overrides)
    return GradeInputs(**base)  # type: ignore[arg-type]


def test_success(grader: ReachGrader) -> None:
    g = grader.grade(_inputs())
    assert g.success is True
    assert g.outcome == Outcome.SUCCESS
    assert g.failure_category is None
    assert "0.05" in g.rule


def test_timeout(grader: ReachGrader) -> None:
    g = grader.grade(
        _inputs(
            terminated=False, truncated=True, success=False, steps=400, final_ee_target_dist_m=0.2
        )
    )
    assert g.success is False
    assert g.outcome == Outcome.TIMEOUT
    assert g.failure_category == "TIMEOUT"


def test_collision_takes_precedence_over_timeout(grader: ReachGrader) -> None:
    g = grader.grade(
        _inputs(
            terminated=False,
            truncated=True,
            success=False,
            steps=400,
            collision_steps=3,
            max_collision_count=1,
        )
    )
    assert g.outcome == Outcome.COLLISION


def test_target_not_reached(grader: ReachGrader) -> None:
    g = grader.grade(
        _inputs(
            terminated=False, truncated=False, success=False, steps=12, final_ee_target_dist_m=0.4
        )
    )
    assert g.outcome == Outcome.TARGET_NOT_REACHED


def test_simulator_error_is_infrastructure(grader: ReachGrader) -> None:
    g = grader.grade(_inputs(simulator_error=True, error_message="boom"))
    assert g.outcome == Outcome.SIMULATOR_ERROR
    assert is_infrastructure_failure(g.outcome) is True
    assert "boom" in g.explanation


def test_numerical_failure_is_infrastructure(grader: ReachGrader) -> None:
    g = grader.grade(_inputs(numerical_failure=True))
    assert g.outcome == Outcome.NUMERICAL_FAILURE
    assert is_infrastructure_failure(g.outcome) is True


def test_trace_not_finite_triggers_numerical(grader: ReachGrader) -> None:
    g = grader.grade(_inputs(trace_finite=False))
    assert g.outcome == Outcome.NUMERICAL_FAILURE


def test_invalid_action_is_infrastructure(grader: ReachGrader) -> None:
    g = grader.grade(_inputs(invalid_action=True))
    assert g.outcome == Outcome.INVALID_ACTION
    assert is_infrastructure_failure(g.outcome) is True


def test_infrastructure_dominates_success_flag(grader: ReachGrader) -> None:
    # Even if success=True accidentally, a simulator error must win.
    g = grader.grade(_inputs(simulator_error=True, success=True))
    assert g.outcome == Outcome.SIMULATOR_ERROR


def test_success_requires_terminated(grader: ReachGrader) -> None:
    # success=True but not terminated should not be graded SUCCESS.
    g = grader.grade(_inputs(success=True, terminated=False, truncated=True, steps=400))
    assert g.outcome != Outcome.SUCCESS


def test_grader_is_deterministic(grader: ReachGrader) -> None:
    a = grader.grade(_inputs()).to_dict()
    b = grader.grade(_inputs()).to_dict()
    assert a == b


def test_grader_registry() -> None:
    assert isinstance(get_grader("reach"), ReachGrader)
    with pytest.raises(KeyError):
        get_grader("does-not-exist")
