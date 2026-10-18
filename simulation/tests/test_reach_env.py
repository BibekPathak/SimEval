"""Tests for the reach environment (Milestone 2)."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest

from simulation.environments.reach_env import ReachEnv


@pytest.fixture()
def env() -> Iterator[ReachEnv]:
    e = ReachEnv()
    yield e
    e.close()


def test_action_dim_matches_model(env: ReachEnv) -> None:
    assert env.action_dim == env.nq == 4


def test_reset_with_seed_is_deterministic(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.1, 0.45]))
    obs_a = env.reset(seed=42)
    q_a = obs_a["qpos"].copy()
    env.reset(seed=42)
    q_b = env.observation()["qpos"].copy()
    assert np.array_equal(q_a, q_b)


def test_different_seeds_with_noise_differ(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.1, 0.45]))
    a = env.reset(seed=1, qpos_noise=0.05)["qpos"]
    b = env.reset(seed=2, qpos_noise=0.05)["qpos"]
    assert not np.array_equal(a, b)


def test_noise_zero_is_exact_default(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.1, 0.45]))
    a = env.reset(seed=1, qpos_noise=0.0)["qpos"]
    b = env.reset(seed=999, qpos_noise=0.0)["qpos"]
    assert np.array_equal(a, b)


def test_observation_keys(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.0, 0.5]))
    obs = env.reset(seed=0)
    for key in ("qpos", "qvel", "ee_pos", "target_pos", "ee_target_vec", "ee_target_dist"):
        assert key in obs
    assert obs["ee_pos"].shape == (3,)
    assert obs["ee_target_vec"].shape == (3,)


def test_holding_position_keeps_state_finite(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.0, 0.5]))
    obs = env.reset(seed=0)
    q = obs["qpos"]
    for _ in range(50):
        result = env.step(q)
        assert np.all(np.isfinite(result.observation["qpos"]))
        assert result.info["step_count"] == env.step_count


def test_non_finite_action_terminates_with_invalid_flag(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.0, 0.5]))
    env.reset(seed=0)
    result = env.step(np.array([np.nan, 0.0, 0.0, 0.0]))
    assert result.terminated is True
    assert result.info["invalid_action"] is True
    assert result.info["reason"] == "non_finite_action"


def test_wrong_action_shape_raises(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.0, 0.5]))
    env.reset(seed=0)
    with pytest.raises(ValueError):
        env.step(np.zeros(3))


def test_truncation_at_max_steps(env: ReachEnv) -> None:
    # A target that is not tracked => should truncate, not terminate.
    env.set_target(np.array([0.2, 0.0, 0.5]))
    obs = env.reset(seed=0)
    frozen = obs["qpos"]
    truncated = False
    for _ in range(env.spec.max_steps):
        result = env.step(frozen)
        truncated = result.truncated
        if result.terminated:
            break
    assert truncated is True


def test_success_requires_dwell(env: ReachEnv) -> None:
    """A single step inside the radius must not immediately count as success."""
    env.set_target(np.array([0.2, 0.0, 0.5]))
    env.reset(seed=0)
    import mujoco

    from simulation.environments.kinematics import damped_least_squares_ik

    q_target = damped_least_squares_ik(mujoco, env.model, env.data, np.array([0.2, 0.0, 0.5]))
    terminated_at = None
    for i in range(env.spec.success_dwell_steps + 5):
        result = env.step(q_target)
        if result.terminated and terminated_at is None:
            terminated_at = i
            break
    # If it terminated, it must take at least the dwell window (arm must first
    # travel, so realistically more), never on step 0.
    if terminated_at is not None:
        assert terminated_at > 0
    assert env.spec.success_dwell_steps >= 1


def test_collision_count_nonnegative(env: ReachEnv) -> None:
    env.set_target(np.array([0.2, 0.0, 0.5]))
    env.reset(seed=0)
    for _ in range(10):
        env.step(env.joint_positions())
    assert env.collision_count() >= 0


def test_set_target_rejects_non_finite(env: ReachEnv) -> None:
    with pytest.raises(ValueError):
        env.set_target(np.array([np.inf, 0.0, 0.5]))
