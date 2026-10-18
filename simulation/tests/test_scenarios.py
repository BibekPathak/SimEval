"""Tests for versioned scenario generation (Milestone 2)."""

from __future__ import annotations

import numpy as np
import pytest

from simulation.scenarios.generator import (
    ScenarioSuite,
    assert_no_leakage,
    generate_suite,
    load_suite,
    save_suite,
)


def test_suite_generation_is_deterministic() -> None:
    a = generate_suite(n_scenarios=20)
    b = generate_suite(n_scenarios=20)
    assert a.content_hash() == b.content_hash()
    assert [s.to_dict() for s in a.scenarios] == [s.to_dict() for s in b.scenarios]


def test_different_base_seed_changes_suite() -> None:
    a = generate_suite(n_scenarios=20, base_seed=1000)
    b = generate_suite(n_scenarios=20, base_seed=2000)
    assert a.content_hash() != b.content_hash()


def test_suite_has_all_splits() -> None:
    suite = generate_suite(n_scenarios=40)
    counts = suite.counts()
    assert set(counts) == {"dev", "validation", "held_out"}
    assert sum(counts.values()) == 40


def test_split_assignment_has_no_leakage() -> None:
    suite = generate_suite(n_scenarios=100)
    # Should not raise.
    assert_no_leakage(suite)


def test_no_leakage_detects_duplicate_seed_across_splits() -> None:
    suite = generate_suite(n_scenarios=10)
    # Force a duplicate seed with a conflicting split to simulate a bug.
    bad = suite.scenarios[0]
    from dataclasses import replace

    conflicting = replace(bad, scenario_id="dup-1", split="held_out")
    tainted = ScenarioSuite(
        suite_name=suite.suite_name,
        suite_version=suite.suite_version,
        task_name=suite.task_name,
        task_version=suite.task_version,
        scenarios=[bad, conflicting],
    )
    with pytest.raises(ValueError, match="leakage"):
        assert_no_leakage(tainted)


def test_duplicate_ids_detected() -> None:
    suite = generate_suite(n_scenarios=5)
    from dataclasses import replace

    dup = replace(suite.scenarios[0], seed=suite.scenarios[0].seed + 999)
    tainted = ScenarioSuite(
        suite_name=suite.suite_name,
        suite_version=suite.suite_version,
        task_name=suite.task_name,
        task_version=suite.task_version,
        scenarios=[suite.scenarios[0], dup],
    )
    with pytest.raises(ValueError, match="duplicate"):
        assert_no_leakage(tainted)


def test_difficulty_tiers_present() -> None:
    suite = generate_suite(n_scenarios=30)
    tiers = {s.difficulty for s in suite.scenarios}
    assert tiers == {"easy", "medium", "hard"}


def test_hard_tiers_have_adversarial_start() -> None:
    suite = generate_suite(n_scenarios=30)
    easy = [s for s in suite.scenarios if s.difficulty == "easy"]
    hard = [s for s in suite.scenarios if s.difficulty == "hard"]
    assert all(s.initial_qpos is None for s in easy)
    assert all(s.initial_qpos is not None for s in hard)


def test_targets_within_reachable_shell() -> None:
    suite = generate_suite(n_scenarios=60)
    for s in suite.scenarios:
        r = float(np.linalg.norm(s.target_position[:2]))
        assert 0.0 < r <= 0.45 + 1e-6
        assert 0.15 <= s.target_position[2] <= 0.65


def test_roundtrip_save_load(tmp_path) -> None:
    suite = generate_suite(n_scenarios=12)
    path = tmp_path / "suite.json"
    save_suite(suite, str(path))
    loaded = load_suite(str(path))
    assert loaded.content_hash() == suite.content_hash()


def test_get_by_id_and_split() -> None:
    suite = generate_suite(n_scenarios=20)
    first = suite.scenarios[0]
    assert suite.get(first.scenario_id) is first
    with pytest.raises(KeyError):
        suite.get("nope")
    assert len(suite.by_split("dev")) == suite.counts().get("dev", 0)


def test_scenario_content_hash_is_stable() -> None:
    s = generate_suite(n_scenarios=1).scenarios[0]
    assert s.content_hash() == s.content_hash()
