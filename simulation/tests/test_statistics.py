"""Tests for statistical utilities (Wilson CI, paired bootstrap)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from simulation.metrics.statistics import (
    Interval,
    paired_bootstrap_interval,
    wilson_interval,
)


def _lo(ci: Interval) -> float:
    assert ci.low is not None
    return ci.low


def _hi(ci: Interval) -> float:
    assert ci.high is not None
    return ci.high


def _est(ci: Interval) -> float:
    assert ci.estimate is not None
    return ci.estimate


def test_wilson_bounds_within_unit_interval() -> None:
    for successes, n in [(0, 10), (10, 10), (5, 10), (1, 3), (0, 1)]:
        ci = wilson_interval(successes, n)
        assert -1e-12 <= _lo(ci) <= _est(ci) + 1e-12
        assert _est(ci) - 1e-12 <= _hi(ci) <= 1.0 + 1e-12


def test_wilson_estimate_is_proportion() -> None:
    ci = wilson_interval(3, 10)
    assert _est(ci) == pytest.approx(0.3)


def test_wilson_zero_n_is_none() -> None:
    ci = wilson_interval(0, 0)
    assert ci.estimate is None and ci.low is None and ci.high is None


def test_wilson_all_success_high_low_reasonable() -> None:
    ci = wilson_interval(10, 10)
    assert _hi(ci) == pytest.approx(1.0, abs=1e-9)
    assert _lo(ci) < 1.0
    # For 10/10 the Wilson lower bound is around 0.72, not 1.0.
    assert 0.6 < _lo(ci) < 0.8


def test_wilson_narrows_with_more_samples() -> None:
    small = wilson_interval(5, 10)
    large = wilson_interval(500, 1000)
    assert (_hi(large) - _lo(large)) < (_hi(small) - _lo(small))


def test_wilson_not_wider_than_naive_at_extremes() -> None:
    # Naive normal interval would be degenerate at p=1; Wilson is not.
    ci = wilson_interval(20, 20)
    assert _hi(ci) - _lo(ci) > 0.0


def test_paired_bootstrap_zero_difference() -> None:
    a = [1.0, 2.0, 3.0, 4.0, 5.0]
    ci = paired_bootstrap_interval(a, a)
    assert _est(ci) == pytest.approx(0.0)
    assert _lo(ci) == pytest.approx(0.0)
    assert _hi(ci) == pytest.approx(0.0)


def test_paired_bootstrap_positive_shift() -> None:
    a = [0.0] * 50
    b = [1.0] * 50
    ci = paired_bootstrap_interval(a, b)
    assert _est(ci) == pytest.approx(1.0)
    assert _lo(ci) == pytest.approx(1.0)
    assert _hi(ci) == pytest.approx(1.0)


def test_paired_bootstrap_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(0, 1, 100).tolist()
    b = rng.normal(0.5, 1, 100).tolist()
    ci1 = paired_bootstrap_interval(a, b, seed=7)
    ci2 = paired_bootstrap_interval(a, b, seed=7)
    assert (ci1.low, ci1.high) == (ci2.low, ci2.high)


def test_paired_bootstrap_interval_ordering() -> None:
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 200).tolist()
    b = rng.normal(0.3, 1, 200).tolist()
    ci = paired_bootstrap_interval(a, b)
    assert _lo(ci) <= _est(ci) <= _hi(ci)


def test_paired_bootstrap_mismatched_lengths() -> None:
    ci = paired_bootstrap_interval([1.0, 2.0], [1.0])
    assert ci.estimate is None


def test_paired_bootstrap_includes_zero_for_noise() -> None:
    rng = np.random.default_rng(3)
    a = rng.normal(0, 1, 50)
    b = a + rng.normal(0, 0.01, 50)  # essentially no effect
    ci = paired_bootstrap_interval(a.tolist(), b.tolist())
    assert _lo(ci) < 0 < _hi(ci)


def test_interval_to_dict() -> None:
    ci = Interval(0.5, 0.3, 0.7, 0.95, "wilson")
    d = ci.to_dict()
    assert d["estimate"] == 0.5 and d["method"] == "wilson"
    assert math.isfinite(d["high"])
