"""Tests for the Milestone 8 learning pipeline.

Covers the MLP training primitives (deterministic, real forward/backward), the
dataset manifest/checksum round-trip, and the behavior-cloning policy interface.
Simulator-heavy DAgger training is exercised by scripts, not unit tests, to keep
the suite fast.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from simulation.datasets.bc_dataset import (
    DATASET_SCHEMA_VERSION,
    DatasetManifest,
    load_dataset,
    save_dataset,
)
from simulation.environments.reach_env import ReachEnv
from simulation.learning.mlp import (
    MODEL_SCHEMA_VERSION,
    TrainConfig,
    load_checkpoint,
    predict,
    save_checkpoint,
    train_mlp,
)


def _make_data(n: int = 200, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, 12))
    # A learnable linear-plus-nonlinear target.
    w = rng.normal(size=(12, 4))
    y = np.tanh(x @ w) + 0.1 * rng.normal(size=(n, 4))
    return x, y


def test_train_reduces_loss() -> None:
    x, y = _make_data()
    _ckpt, history = train_mlp(x, y, TrainConfig(epochs=60, seed=1))
    assert history.train_loss[-1] < history.train_loss[0]


def test_training_is_deterministic() -> None:
    x, y = _make_data()
    c1, h1 = train_mlp(x, y, TrainConfig(epochs=30, seed=7))
    c2, h2 = train_mlp(x, y, TrainConfig(epochs=30, seed=7))
    assert h1.best_val_loss == h2.best_val_loss
    assert c1["params"][0]["w"] == c2["params"][0]["w"]


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    x, y = _make_data()
    ckpt, _ = train_mlp(x, y, TrainConfig(epochs=20, seed=2))
    path = save_checkpoint(ckpt, tmp_path / "m.json")
    loaded = load_checkpoint(path)
    assert loaded["schema_version"] == MODEL_SCHEMA_VERSION
    assert loaded["input_dim"] == 12 and loaded["output_dim"] == 4


def test_predict_shape_and_finiteness() -> None:
    x, y = _make_data()
    ckpt, _ = train_mlp(x, y, TrainConfig(epochs=20, seed=3))
    out = predict(ckpt, x[:5])
    assert out.shape == (5, 4)
    assert np.all(np.isfinite(out))


def test_predict_is_deterministic() -> None:
    x, y = _make_data()
    ckpt, _ = train_mlp(x, y, TrainConfig(epochs=20, seed=4))
    assert np.array_equal(predict(ckpt, x[:3]), predict(ckpt, x[:3]))


def test_bad_checkpoint_schema_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"schema_version": "999"}))
    with pytest.raises(ValueError, match="schema"):
        load_checkpoint(path)


def test_train_requires_enough_samples() -> None:
    with pytest.raises(ValueError):
        train_mlp(np.zeros((2, 12)), np.zeros((2, 4)))


def test_dataset_roundtrip_and_checksum(tmp_path: Path) -> None:
    arrays = {"features": np.ones((5, 12)), "labels": np.zeros((5, 4))}
    manifest = DatasetManifest(
        schema_version=DATASET_SCHEMA_VERSION,
        expert_policy="ik_planner_baseline",
        expert_version="v1",
        task_name="reach",
        task_version="v1",
        suite_name="s",
        suite_version="v1",
        suite_hash="abc",
        split="dev",
        base_seed=1,
        control_stride=2,
        n_episodes=1,
        n_samples=0,
        feature_names=[],
        label_names=[],
        checksum_sha256="",
    )
    save_dataset(arrays, directory=tmp_path, manifest=manifest)
    loaded, man = load_dataset(tmp_path)
    assert man.n_samples == 5
    assert set(loaded) == {"features", "labels"}
    assert man.checksum_sha256 != ""


def test_dataset_checksum_detects_corruption(tmp_path: Path) -> None:
    arrays = {"features": np.ones((5, 12)), "labels": np.zeros((5, 4))}
    manifest = DatasetManifest(
        schema_version="1",
        expert_policy="e",
        expert_version="v1",
        task_name="reach",
        task_version="v1",
        suite_name="s",
        suite_version="v1",
        suite_hash="abc",
        split="dev",
        base_seed=1,
        control_stride=2,
        n_episodes=1,
        n_samples=0,
        feature_names=[],
        label_names=[],
        checksum_sha256="",
    )
    save_dataset(arrays, directory=tmp_path, manifest=manifest)
    # Corrupt the stored arrays.
    np.savez_compressed(tmp_path / "data.npz", features=np.zeros((5, 12)), labels=np.zeros((5, 4)))
    with pytest.raises(ValueError, match="checksum"):
        load_dataset(tmp_path)


@pytest.fixture()
def env() -> Iterator[ReachEnv]:
    e = ReachEnv()
    e.set_target(np.array([0.2, 0.1, 0.5]))
    yield e
    e.close()


def test_behavior_cloning_policy_loads_and_acts(env: ReachEnv, tmp_path: Path) -> None:
    from simulation.policies.behavior_cloning import BehaviorCloningConfig, BehaviorCloningPolicy

    x, y = _make_data()
    ckpt, _ = train_mlp(x, y, TrainConfig(epochs=10, seed=5))
    path = save_checkpoint(ckpt, tmp_path / "bc.json")

    policy = BehaviorCloningPolicy(
        BehaviorCloningConfig(checkpoint=str(path)), env.kinematics_context()
    )
    obs = env.reset(seed=0)
    action = policy.act(obs)
    assert action.shape == (env.action_dim,)
    assert np.all(np.isfinite(action))


def test_behavior_cloning_missing_checkpoint_raises(tmp_path: Path) -> None:
    from simulation.policies.behavior_cloning import BehaviorCloningConfig, BehaviorCloningPolicy

    with pytest.raises(FileNotFoundError):
        BehaviorCloningPolicy(
            BehaviorCloningConfig(checkpoint=str(tmp_path / "nope.json")),
            None,  # type: ignore[arg-type]
        )


def test_registry_includes_behavior_cloning() -> None:
    from simulation.policies.registry import available_policies

    names = {p["name"] for p in available_policies()}
    assert "behavior_cloning" in names
