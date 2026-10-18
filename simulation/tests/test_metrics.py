"""Tests for metric computation. These do not require the simulator."""

from __future__ import annotations

import math

import pytest

from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.outcome import EpisodeResult, Outcome


def _episode(
    *,
    success: bool,
    outcome: str,
    steps: int,
    wall: float = 0.1,
    return_sum: float = 0.0,
    collision_steps: int = 0,
    failure_category: str | None = None,
    inference_s: float = 0.001,
) -> EpisodeResult:
    return EpisodeResult(
        episode_id="e",
        experiment_id="x",
        scenario_id="s",
        policy_name="p",
        policy_version="v1",
        task_name="reach",
        task_version="v1",
        seed=0,
        split="dev",
        difficulty="easy",
        success=success,
        outcome=outcome,
        failure_category=failure_category,
        explanation="",
        rule="",
        steps=steps,
        wall_clock_s=wall,
        sim_time_s=steps * 0.005,
        return_sum=return_sum,
        min_ee_target_dist_m=0.0,
        final_ee_target_dist_m=0.0,
        initial_ee_target_dist_m=0.3,
        collision_steps=collision_steps,
        max_collision_count=collision_steps,
        policy_inference_s=inference_s,
    )


def test_success_rate_numerator_denominator() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=10, return_sum=1.0),
        _episode(success=True, outcome="SUCCESS", steps=20, return_sum=1.0),
        _episode(success=False, outcome="TIMEOUT", steps=400, failure_category="TIMEOUT"),
        _episode(success=False, outcome="TIMEOUT", steps=400, failure_category="TIMEOUT"),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.n_episodes_evaluated == 4
    assert m.n_success == 2
    assert m.success_rate == pytest.approx(0.5)
    assert m.failure_rate == pytest.approx(0.5)
    assert m.failure_categories == {"TIMEOUT": 2}


def test_infrastructure_failures_excluded_by_default() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=10, return_sum=1.0),
        _episode(
            success=False, outcome="SIMULATOR_ERROR", steps=0, failure_category="SIMULATOR_ERROR"
        ),
        _episode(
            success=False, outcome="INVALID_ACTION", steps=1, failure_category="INVALID_ACTION"
        ),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.n_episodes_total == 3
    assert m.n_infrastructure_failures == 2
    assert m.n_episodes_evaluated == 1
    assert m.n_success == 1
    assert m.success_rate == pytest.approx(1.0)


def test_infrastructure_failures_included_when_requested() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=10, return_sum=1.0),
        _episode(
            success=False, outcome="SIMULATOR_ERROR", steps=0, failure_category="SIMULATOR_ERROR"
        ),
    ]
    m = compute_metrics(eps, timestep_s=0.005, include_infrastructure=True)
    assert m.n_episodes_evaluated == 2
    assert m.success_rate == pytest.approx(0.5)


def test_completion_time_only_over_successes() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=100, return_sum=1.0),
        _episode(success=True, outcome="SUCCESS", steps=200, return_sum=1.0),
        _episode(success=False, outcome="TIMEOUT", steps=400, failure_category="TIMEOUT"),
    ]
    m = compute_metrics(eps, timestep_s=0.01)
    # successful completion times: 1.0s and 2.0s -> mean 1.5
    assert m.completion_time_mean_s == pytest.approx(1.5)
    assert m.completion_time_median_s == pytest.approx(1.5)


def test_episode_length_mean_includes_failures() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=100, return_sum=1.0),
        _episode(success=False, outcome="TIMEOUT", steps=400, failure_category="TIMEOUT"),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.episode_length_mean_steps == pytest.approx(250.0)


def test_collision_rate() -> None:
    eps = [
        _episode(
            success=False,
            outcome="COLLISION",
            steps=50,
            collision_steps=5,
            failure_category="COLLISION",
        ),
        _episode(success=True, outcome="SUCCESS", steps=50, return_sum=1.0, collision_steps=0),
        _episode(
            success=False,
            outcome="COLLISION",
            steps=50,
            collision_steps=2,
            failure_category="COLLISION",
        ),
        _episode(success=True, outcome="SUCCESS", steps=50, return_sum=1.0, collision_steps=0),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.collision_rate == pytest.approx(0.5)
    assert m.mean_collision_steps == pytest.approx((5 + 2) / 4)


def test_return_mean_and_median() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=10, return_sum=1.0),
        _episode(
            success=False, outcome="TIMEOUT", steps=400, return_sum=0.0, failure_category="TIMEOUT"
        ),
        _episode(success=True, outcome="SUCCESS", steps=10, return_sum=1.0),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.return_mean == pytest.approx(2.0 / 3.0)
    assert m.return_median == pytest.approx(1.0)


def test_throughput_and_timing() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=10, wall=0.5, return_sum=1.0),
        _episode(success=True, outcome="SUCCESS", steps=10, wall=0.5, return_sum=1.0),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.mean_wall_clock_s == pytest.approx(0.5)
    assert m.throughput_eps_per_s == pytest.approx(2.0)  # 2 episodes / 1.0s
    assert m.mean_policy_inference_ms == pytest.approx(1.0)


def test_empty_episode_list() -> None:
    m = compute_metrics([], timestep_s=0.005)
    assert m.n_episodes_total == 0
    assert m.success_rate is None
    assert m.failure_categories == {}


def test_only_infrastructure_failures() -> None:
    eps = [
        _episode(
            success=False, outcome="SIMULATOR_ERROR", steps=0, failure_category="SIMULATOR_ERROR"
        ),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    assert m.n_episodes_evaluated == 0
    assert m.success_rate is None
    assert m.n_infrastructure_failures == 1


def test_metrics_are_finite() -> None:
    eps = [
        _episode(success=True, outcome="SUCCESS", steps=10, return_sum=1.0),
    ]
    m = compute_metrics(eps, timestep_s=0.005)
    for key, value in m.to_dict().items():
        if isinstance(value, float) and value is not None:
            assert math.isfinite(value), key


def test_outcome_enum_roundtrip() -> None:
    e = _episode(success=True, outcome=Outcome.SUCCESS.value, steps=1, return_sum=1.0)
    m = compute_metrics([e], timestep_s=0.005)
    assert m.n_success == 1
