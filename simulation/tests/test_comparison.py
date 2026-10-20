"""Tests for the scenario-paired comparison and regression detection engine."""

from __future__ import annotations

import pytest

from simulation.metrics.comparison import (
    ComparisonConfig,
    PairedScenario,
    build_report,
)


def _pair(
    sid: str,
    *,
    a_success: bool,
    b_success: bool,
    a_return: float = 0.0,
    b_return: float = 0.0,
    a_steps: float = 100.0,
    b_steps: float = 100.0,
    a_collision: float = 0.0,
    b_collision: float = 0.0,
    a_infra: bool = False,
    b_infra: bool = False,
) -> PairedScenario:
    return PairedScenario(
        scenario_id=sid,
        a_success=a_success,
        b_success=b_success,
        a_return=a_return,
        b_return=b_return,
        a_steps=a_steps,
        b_steps=b_steps,
        a_collision=a_collision,
        b_collision=b_collision,
        a_completion_s=a_steps,
        b_completion_s=b_steps,
        a_infrastructure_failure=a_infra,
        b_infrastructure_failure=b_infra,
    )


def _metric(report, name):
    return next(m for m in report.metrics if m.metric == name)


def test_clear_improvement_is_detected() -> None:
    pairs = [
        _pair(f"s{i}", a_success=(i % 3 != 0), b_success=True, a_return=0.6, b_return=1.0)
        for i in range(60)
    ]
    report = build_report(pairs)
    assert report.sufficient_evidence is True
    assert _metric(report, "success_rate").verdict == "IMPROVED"


def test_clear_regression_is_detected() -> None:
    pairs = [
        _pair(f"s{i}", a_success=True, b_success=(i % 4 != 0), a_return=1.0, b_return=0.75)
        for i in range(60)
    ]
    report = build_report(pairs)
    assert _metric(report, "success_rate").verdict == "REGRESSED"
    assert _metric(report, "return_mean").verdict == "REGRESSED"


def test_no_change_is_inconclusive() -> None:
    pairs = [_pair(f"s{i}", a_success=True, b_success=True) for i in range(60)]
    report = build_report(pairs)
    assert _metric(report, "success_rate").verdict == "INCONCLUSIVE"


def test_small_sample_is_inconclusive_with_warning() -> None:
    pairs = [_pair(f"s{i}", a_success=False, b_success=True) for i in range(5)]
    report = build_report(pairs)
    assert report.sufficient_evidence is False
    assert any("below the minimum" in w for w in report.warnings)
    assert _metric(report, "success_rate").verdict == "INCONCLUSIVE"


def test_infrastructure_failures_excluded() -> None:
    pairs = [_pair(f"s{i}", a_success=True, b_success=True) for i in range(20)]
    pairs.append(_pair("bad", a_success=False, b_success=False, b_infra=True))
    report = build_report(pairs)
    assert any("infrastructure failures" in w for w in report.warnings)
    sr = _metric(report, "success_rate")
    assert sr.n_pairs == 20


def test_all_infrastructure_is_no_evidence() -> None:
    pairs = [_pair(f"s{i}", a_success=False, b_success=False, a_infra=True) for i in range(5)]
    report = build_report(pairs)
    assert report.sufficient_evidence is False
    assert "no comparable scenarios" in report.summary.lower()


def test_direction_aware_collision_regression() -> None:
    # Lower collision is better; b collides more => regression.
    pairs = [
        _pair(f"s{i}", a_success=True, b_success=True, a_collision=0.0, b_collision=3.0)
        for i in range(40)
    ]
    report = build_report(pairs)
    assert _metric(report, "collision_rate").verdict == "REGRESSED"


def test_lower_is_better_improvement() -> None:
    pairs = [
        _pair(f"s{i}", a_success=True, b_success=True, a_steps=300, b_steps=120) for i in range(40)
    ]
    report = build_report(pairs)
    assert _metric(report, "episode_length_mean_steps").verdict == "IMPROVED"


def test_below_threshold_is_inconclusive() -> None:
    # Exactly 1 scenario flips (1/200 = 0.005) — supported? even if so, tiny and
    # well under the 0.02 threshold, so it must not be called an improvement.
    pairs = [_pair(f"s{i}", a_success=True, b_success=True) for i in range(200)]
    pairs[0] = _pair("s0", a_success=False, b_success=True)
    report = build_report(pairs)
    sr = _metric(report, "success_rate")
    assert sr.delta == pytest.approx(0.005)
    assert sr.verdict == "INCONCLUSIVE"


def test_report_is_deterministic() -> None:
    pairs = [_pair(f"s{i}", a_success=(i % 2 == 0), b_success=(i % 3 == 0)) for i in range(30)]
    r1 = build_report(pairs)
    r2 = build_report(pairs)
    assert [m.to_dict() for m in r1.metrics] == [m.to_dict() for m in r2.metrics]


def test_per_arm_intervals_present() -> None:
    pairs = [_pair(f"s{i}", a_success=(i % 2 == 0), b_success=True) for i in range(30)]
    report = build_report(pairs)
    a_ci = _metric(report, "success_rate_a")
    b_ci = _metric(report, "success_rate_b")
    assert a_ci.ci_low is not None and a_ci.ci_high is not None
    assert b_ci.ci_low is not None and b_ci.ci_high is not None


def test_completion_time_uses_both_succeeded_pairs() -> None:
    pairs = [
        _pair(f"s{i}", a_success=True, b_success=True, a_steps=200, b_steps=100) for i in range(20)
    ]
    pairs += [_pair(f"f{i}", a_success=True, b_success=False) for i in range(5)]
    report = build_report(pairs)
    ct = _metric(report, "completion_time_mean_s")
    assert ct.n_pairs == 20  # only scenarios where both succeeded
    assert ct.verdict == "IMPROVED"


def test_custom_thresholds() -> None:
    cfg = ComparisonConfig()
    cfg.thresholds["success_rate"]["improvement_threshold"] = 0.001
    pairs = [_pair(f"s{i}", a_success=False, b_success=True) for i in range(30)]
    report = build_report(pairs, config=cfg)
    assert _metric(report, "success_rate").verdict == "IMPROVED"


def test_summary_mentions_scenario_count() -> None:
    pairs = [_pair(f"s{i}", a_success=True, b_success=True) for i in range(25)]
    report = build_report(pairs)
    assert "25 paired scenarios" in report.summary
