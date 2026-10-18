"""Tests for the local artifact store."""

from __future__ import annotations

import numpy as np
import pytest

from simulation.artifacts.store import ARTIFACT_SCHEMA_VERSION, LocalArtifactStore


def test_put_get_arrays_roundtrip(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    arrays = {
        "qpos": np.arange(8, dtype=float).reshape(2, 4),
        "ee_pos": np.zeros((2, 3)),
        "reward": np.array([0.0, 1.0]),
    }
    ref = store.put_arrays("exp/episodes/e1", arrays)
    assert store.exists(ref)
    loaded = store.get_arrays(ref)
    assert set(loaded) == set(arrays)
    for key in arrays:
        assert np.array_equal(loaded[key], arrays[key])


def test_metadata_roundtrip(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    meta = {"scenario": "s1", "success": True, "n": np.int64(3), "d": np.float64(1.5)}
    ref = store.put_metadata("exp/meta", meta)
    loaded = store.get_metadata(ref)
    assert loaded["scenario"] == "s1"
    assert loaded["success"] is True
    assert loaded["n"] == 3
    assert loaded["d"] == 1.5


def test_missing_artifact_not_exists(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    assert store.exists("does/not/exist.npz") is False


def test_absolute_key_rejected(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.put_arrays("/etc/passwd", {"a": np.zeros(1)})


def test_traversal_key_rejected(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    with pytest.raises(ValueError):
        store.put_arrays("../../escape", {"a": np.zeros(1)})


def test_schema_version_present_but_hidden(tmp_path) -> None:
    store = LocalArtifactStore(tmp_path)
    ref = store.put_arrays("e", {"a": np.zeros(1)})
    loaded = store.get_arrays(ref)
    assert "__schema_version__" not in loaded
    assert ARTIFACT_SCHEMA_VERSION == "1"
