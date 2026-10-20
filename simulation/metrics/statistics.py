"""Statistical utilities for policy comparison.

Design principles
-----------------
* **Scenario is the independent unit.** Timesteps within an episode are
  correlated; episodes across distinct scenarios are treated as the resampling
  unit. Paired comparisons resample *scenarios*, never timesteps.
* **Deterministic.** Bootstrap uses a fixed seed, so repeated comparisons over
  the same data return identical intervals.
* **No significance theatre.** We report intervals and effect sizes and only
  assert an improvement when a defined procedure supports it. When the sample is
  too small, we say so rather than over-claiming.

Methods
-------
* Success rate (binary): **Wilson score interval** — well-behaved at small n and
  near 0/1, unlike the naive normal approximation.
* Continuous metrics (paired, per scenario): **paired bootstrap** over scenario
  differences — resample scenarios with replacement, compute the mean difference,
  and take percentile intervals.
* Success-rate difference (paired): bootstrap over paired per-scenario outcomes
  (b - a) using the same scenario resampling.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Interval:
    """A point estimate with a confidence interval."""

    estimate: float | None
    low: float | None
    high: float | None
    confidence: float
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimate": self.estimate,
            "low": self.low,
            "high": self.high,
            "confidence": self.confidence,
            "method": self.method,
        }


@dataclass
class MetricComparison:
    """Comparison of one metric between two experiments (b relative to a)."""

    metric: str
    unit: str
    direction: str  # "higher_is_better" | "lower_is_better" | "neutral"
    a: float | None
    b: float | None
    delta: float | None  # b - a
    relative: float | None  # (b - a) / |a| when meaningful
    ci_low: float | None
    ci_high: float | None
    confidence: float
    method: str
    n_pairs: int
    verdict: str  # "IMPROVED" | "REGRESSED" | "INCONCLUSIVE" | "MISSING"
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "unit": self.unit,
            "direction": self.direction,
            "a": self.a,
            "b": self.b,
            "delta": self.delta,
            "relative": self.relative,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "confidence": self.confidence,
            "method": self.method,
            "n_pairs": self.n_pairs,
            "verdict": self.verdict,
            "reason": self.reason,
        }


@dataclass
class Report:
    """A whole comparison report with an overall evidence verdict."""

    metrics: list[MetricComparison] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sufficient_evidence: bool = False
    summary: str = ""


def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> Interval:
    """Wilson score interval for a binomial proportion.

    Handles n == 0 and extreme proportions without producing out-of-range values.
    """
    if n <= 0:
        return Interval(None, None, None, confidence, "wilson")
    z = _z_for(confidence)
    phat = successes / n
    denom = 1.0 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)) / denom
    return Interval(
        estimate=float(phat),
        low=float(max(0.0, centre - margin)),
        high=float(min(1.0, centre + margin)),
        confidence=confidence,
        method="wilson",
    )


def paired_bootstrap_interval(
    a_values: Sequence[float],
    b_values: Sequence[float],
    *,
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 12345,
) -> Interval:
    """Paired bootstrap interval for the mean difference ``mean(b - a)``.

    Requires equal-length, index-aligned (paired) sequences. Resamples *pairs*,
    preserving the pairing structure.
    """
    a = np.asarray(a_values, dtype=float)
    b = np.asarray(b_values, dtype=float)
    if a.shape != b.shape or a.size == 0:
        return Interval(None, None, None, confidence, "paired_bootstrap")
    diffs = b - a
    rng = np.random.default_rng(seed)
    n = diffs.size
    idx = rng.integers(0, n, size=(n_resamples, n))
    samples = diffs[idx].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    low, high = np.percentile(samples, [alpha * 100.0, (1.0 - alpha) * 100.0])
    return Interval(
        estimate=float(diffs.mean()),
        low=float(low),
        high=float(high),
        confidence=confidence,
        method="paired_bootstrap",
    )


def _paired_success_bootstrap(
    a_success: Sequence[bool],
    b_success: Sequence[bool],
    *,
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 12345,
) -> Interval:
    """Paired bootstrap for the success-rate difference (b - a)."""
    a = np.asarray(a_success, dtype=float)
    b = np.asarray(b_success, dtype=float)
    if a.shape != b.shape or a.size == 0:
        return Interval(None, None, None, confidence, "paired_bootstrap_success")
    return paired_bootstrap_interval(
        float(a.tolist()),
        float(b.tolist()),
        confidence=confidence,
        n_resamples=n_resamples,
        seed=seed,
    )


def _z_for(confidence: float) -> float:
    # Two-sided z critical value from an inverse normal CDF approximation.
    # Accurate to ~1e-3 for common confidence levels; sufficient for reporting.
    from statistics import NormalDist

    return NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)


__all__ = [
    "Interval",
    "MetricComparison",
    "Report",
    "paired_bootstrap_interval",
    "wilson_interval",
]
