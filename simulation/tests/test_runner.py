"""Integration tests for the episode runner.

These execute real MuJoCo rollouts. They assert that metrics derive from actual
recorded data, that failures never inflate success, and that results are
reproducible for a fixed deterministic configuration.
"""

from __future__ import annotations

import numpy as np
import pytest

from simulation.artifacts.store import LocalArtifactStore
from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.episode_runner import EpisodeConfig, run_episode
from simulation.runners.outcome import Outcome, is_infrastructure_failure
from simulation.scenarios.generator import generate_suite


@pytest.fixture(scope="module")
def suite():
    return generate_suite(n_scenarios=12)


@pytest.fixture()
def store(tmp_path) -> LocalArtifactStore:
    return LocalArtifactStore(tmp_path)


def test_episode_runs_and_is_graded(suite, store) -> None:
    sc = suite.scenarios[0]
    result = run_episode(
        scenario=sc,
        policy_name="ik_planner_baseline",
        store=store,
        experiment_id="exp",
    )
    assert result.outcome in {o.value for o in Outcome}
    assert result.episode_id
    assert result.scenario_id == sc.scenario_id
    assert result.steps >= 1
    assert result.wall_clock_s > 0
    assert result.sim_time_s == pytest.approx(result.steps * 0.005)


def test_success_episode_is_graded_success(suite, store) -> None:
    # scenario 0 is an easy tier with a reachable target.
    sc = suite.scenarios[0]
    result = run_episode(scenario=sc, policy_name="ik_planner_baseline", store=store)
    assert result.success is True
    assert result.outcome == Outcome.SUCCESS.value
    assert result.final_ee_target_dist_m < 0.05


def test_artifact_is_persisted_and_loadable(suite, store) -> None:
    sc = suite.scenarios[0]
    result = run_episode(scenario=sc, policy_name="ik_planner_baseline", store=store)
    assert result.artifact_ref is not None
    assert store.exists(result.artifact_ref)
    arrays = store.get_arrays(result.artifact_ref)
    for key in ("qpos", "ee_pos", "target_pos", "action", "reward", "collision"):
        assert key in arrays
    # Recorded step count must match episode steps + initial capture.
    assert arrays["qpos"].shape[0] == result.steps + 1


def test_metrics_derive_from_recorded_episodes(suite, store) -> None:
    episodes = [
        run_episode(
            scenario=sc, policy_name="ik_planner_baseline", store=store, experiment_id="exp"
        )
        for sc in suite.scenarios
    ]
    m = compute_metrics(episodes, timestep_s=0.005)
    assert m.n_episodes_total == len(suite.scenarios)
    assert 0.0 <= (m.success_rate or 0.0) <= 1.0
    assert m.n_success == sum(e.success for e in episodes)


def test_timeout_episode_not_counted_as_success(suite, store) -> None:
    timeouts = [
        run_episode(scenario=sc, policy_name="ik_planner_baseline", store=store)
        for sc in suite.scenarios
    ]
    timeouts = [e for e in timeouts if e.outcome == Outcome.TIMEOUT.value]
    if not timeouts:
        pytest.skip("no timeout episodes in this suite")
    for e in timeouts:
        assert e.success is False
        assert e.failure_category == "TIMEOUT"


def test_policy_version_recorded(suite, store) -> None:
    sc = suite.scenarios[0]
    result = run_episode(scenario=sc, policy_name="ik_planner_baseline", store=store)
    assert result.policy_version == "v1"
    assert result.policy_name == "ik_planner_baseline"


def test_reproducible_episode(suite, store) -> None:
    sc = suite.scenarios[0]

    def run():
        return run_episode(
            scenario=sc,
            policy_name="ik_planner_baseline",
            store=store,
            experiment_id="rep",
            episode_id="fixed-id",
        )

    a, b = run(), run()
    assert a.steps == b.steps
    assert a.success == b.success
    assert a.outcome == b.outcome
    # Distances should match to floating-point tolerance.
    assert a.final_ee_target_dist_m == pytest.approx(b.final_ee_target_dist_m, abs=1e-9)


def test_simulator_error_is_infrastructure_and_not_success(suite, store, monkeypatch) -> None:
    from simulation.runners import episode_runner

    sc = suite.scenarios[0]

    class BoomEnv:
        def __init__(self, *a, **k):
            raise RuntimeError("simulated engine failure")

    monkeypatch.setattr(episode_runner, "ReachEnv", BoomEnv)
    result = run_episode(scenario=sc, policy_name="ik_planner_baseline", store=store)

    assert result.success is False
    assert result.outcome == Outcome.SIMULATOR_ERROR.value
    assert is_infrastructure_failure(Outcome(result.outcome)) is True
    assert result.error is not None and "simulated engine failure" in result.error


def test_invalid_action_episode_is_infrastructure(suite, store, monkeypatch) -> None:
    """A policy emitting NaN must be classified INVALID_ACTION, not success."""
    from simulation.policies.base import Policy, PolicyConfig
    from simulation.runners import episode_runner

    sc = suite.scenarios[0]

    class NanPolicy(Policy):
        name = "nan_policy"
        version = "v0"

        def act(self, observation):
            return np.full(4, np.nan)

    monkeypatch.setattr(
        episode_runner,
        "build_policy",
        lambda name, cfg, ctx: NanPolicy(PolicyConfig()),
    )
    result = run_episode(scenario=sc, policy_name="ik_planner_baseline", store=store)

    assert result.success is False
    assert result.outcome == Outcome.INVALID_ACTION.value


def test_capture_every_reduces_artifact_size(suite, store) -> None:
    sc = suite.scenarios[0]
    dense = run_episode(
        scenario=sc,
        policy_name="ik_planner_baseline",
        store=store,
        config=EpisodeConfig(capture_every=1),
    )
    sparse = run_episode(
        scenario=sc,
        policy_name="ik_planner_baseline",
        store=store,
        config=EpisodeConfig(capture_every=50),
    )
    dense_n = store.get_arrays(dense.artifact_ref)["qpos"].shape[0]
    sparse_n = store.get_arrays(sparse.artifact_ref)["qpos"].shape[0]
    assert sparse_n < dense_n


def test_persist_disabled_writes_no_artifact(suite, store) -> None:
    sc = suite.scenarios[0]
    result = run_episode(
        scenario=sc,
        policy_name="ik_planner_baseline",
        store=store,
        config=EpisodeConfig(persist_artifacts=False),
    )
    assert result.artifact_ref is None
