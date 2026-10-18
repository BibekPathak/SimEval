"""Tests for the policy interface and concrete reach policies (Milestone 2)."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest

from simulation.environments.reach_env import ReachEnv
from simulation.policies.base import Policy, PolicyConfig
from simulation.policies.ik_planner import IKPlannerConfig, IKPlannerPolicy
from simulation.policies.registry import (
    available_policies,
    build_policy,
)
from simulation.policies.resolved_rate import ResolvedRateConfig, ResolvedRatePolicy


@pytest.fixture()
def env() -> Iterator[ReachEnv]:
    e = ReachEnv()
    e.set_target(np.array([0.2, 0.1, 0.5]))
    yield e
    e.close()


def test_registry_lists_two_distinct_policies() -> None:
    listed = available_policies()
    names = {p["name"] for p in listed}
    assert names == {"ik_planner_baseline", "resolved_rate_candidate"}
    assert len(listed) == 2


def test_policies_are_constructible_from_config(env: ReachEnv) -> None:
    for name in ("ik_planner_baseline", "resolved_rate_candidate"):
        policy = build_policy(name, {}, env.kinematics_context())
        assert isinstance(policy, Policy)
        cfg = policy.config_dict()
        assert cfg["name"] == name
        # Config must round-trip losslessly through JSON-serializable types.
        assert all(isinstance(v, (str, int, float, bool)) for v in cfg.values())


def test_unknown_policy_raises(env: ReachEnv) -> None:
    with pytest.raises(KeyError):
        build_policy("does-not-exist", {}, env.kinematics_context())


def test_action_shape_and_finiteness(env: ReachEnv) -> None:
    for name in ("ik_planner_baseline", "resolved_rate_candidate"):
        obs = env.reset(seed=3)
        policy = build_policy(name, {}, env.kinematics_context())
        action = policy.act(obs)
        assert action.shape == (env.action_dim,)
        assert np.all(np.isfinite(action))


def test_both_policies_reach_an_easy_target(env: ReachEnv) -> None:
    for name in ("ik_planner_baseline", "resolved_rate_candidate"):
        obs = env.reset(seed=5)
        policy = build_policy(name, {}, env.kinematics_context())
        reached = False
        for _ in range(env.spec.max_steps):
            result = env.step(policy.act(obs))
            obs = result.observation
            if result.terminated:
                reached = True
                break
        assert reached, f"{name} failed to reach easy target"


def test_baseline_is_deterministic(env: ReachEnv) -> None:
    def run() -> np.ndarray:
        obs = env.reset(seed=11)
        policy = build_policy("ik_planner_baseline", {}, env.kinematics_context())
        for _ in range(20):
            result = env.step(policy.act(obs))
            obs = result.observation
        return env.joint_positions()

    assert np.array_equal(run(), run())


def test_candidate_is_deterministic(env: ReachEnv) -> None:
    def run() -> np.ndarray:
        obs = env.reset(seed=11)
        policy = build_policy("resolved_rate_candidate", {}, env.kinematics_context())
        for _ in range(20):
            result = env.step(policy.act(obs))
            obs = result.observation
        return env.joint_positions()

    assert np.array_equal(run(), run())


def test_policies_differ_in_behaviour(env: ReachEnv) -> None:
    """The two policies must not be behaviourally identical."""
    actions = {}
    for name in ("ik_planner_baseline", "resolved_rate_candidate"):
        obs = env.reset(seed=7)
        policy = build_policy(name, {}, env.kinematics_context())
        first = policy.act(obs)
        actions[name] = first
    assert not np.allclose(actions["ik_planner_baseline"], actions["resolved_rate_candidate"])


def test_policy_configs_expose_version() -> None:
    assert IKPlannerConfig().version == "v1"
    assert ResolvedRateConfig().version == "v1"
    assert IKPlannerPolicy.name == "ik_planner_baseline"
    assert ResolvedRatePolicy.name == "resolved_rate_candidate"


def test_config_dict_is_json_serializable() -> None:
    import json

    cfg = IKPlannerConfig()
    json.dumps(cfg.to_dict())
    cfg2 = PolicyConfig(name="x", version="v9")
    assert cfg2.to_dict() == {"name": "x", "version": "v9"}
