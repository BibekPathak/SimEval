"""Tests for the Milestone 1 simulator smoke-test harness.

These tests exercise ``scripts/smoke_sim.py`` directly so that CI fails if the
headless simulation capability regresses. They do not mock MuJoCo: the smoke
test runs real physics.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMOKE_PATH = _REPO_ROOT / "scripts" / "smoke_sim.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("simeval_smoke_sim", _SMOKE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["simeval_smoke_sim"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def smoke():
    return _load_smoke_module()


def test_smoke_report_is_successful(smoke) -> None:
    report = smoke.run(render=False)
    assert report.ok, [(c.name, c.detail) for c in report.checks]


def test_rollout_is_deterministic(smoke) -> None:
    report = smoke.run(render=False)
    assert report.deterministic
    assert report.det_max_abs_diff == 0.0
    assert report.det_qpos_a == report.det_qpos_b


def test_end_effector_reaches_target(smoke) -> None:
    report = smoke.run(render=False)
    assert report.final_ee_target_distance_m < smoke.SUCCESS_DISTANCE_M
    assert report.success is True


def test_model_dimensions_are_expected(smoke) -> None:
    report = smoke.run(render=False)
    assert report.nq == 3
    assert report.nu == 3
    assert report.nbody == 7


def test_json_serializable(smoke) -> None:
    import json
    from dataclasses import asdict

    report = smoke.run(render=False)
    payload = asdict(report)
    payload["checks"] = [asdict(c) for c in report.checks]
    encoded = json.dumps(payload)
    assert "mjcf_hash" in encoded
