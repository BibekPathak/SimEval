"""Scenario-paired policy comparison and regression detection.

This module is pure: it consumes paired per-scenario observations and produces a
:class:`Report` of verdicts. Persistence and experiment loading live in the
backend service.

Definitions
-----------
For a metric with a known direction, we compare candidate ``b`` against baseline
``a`` using the paired scenario differences. A metric is declared:

* ``IMPROVED`` / ``REGRESSED`` when the paired 95% interval excludes zero **and**
  the point effect exceeds the configured regression/improvement threshold for
  that metric, in the direction of "better".
* ``INCONCLUSIVE`` when the interval straddles zero or the effect is within the
  threshold (i.e. we cannot tell a real change from noise), or when there is
  insufficient data.
* ``MISSING`` when either side lacks data.

Thresholds are per metric. A **regression** is a change that is worse than a
``regression_threshold`` and statistically supported. Sample-size adequacy is
reported and gated: below ``min_pairs`` we do not claim improvement/regression.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from simulation.metrics.statistics import (
    Interval,
    MetricComparison,
    Report,
    paired_bootstrap_interval,
    wilson_interval,
)

#: Metric direction and default thresholds.
#: ``higher_is_better`` / ``lower_is_better`` / ``neutral``.
DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    "success_rate": {
        "direction": "higher_is_better",
        "improvement_threshold": 0.02,
        "regression_threshold": 0.02,
        "unit": "ratio",
    },
    "return_mean": {
        "direction": "higher_is_better",
        "improvement_threshold": 0.02,
        "regression_threshold": 0.02,
        "unit": "reward",
    },
    "collision_rate": {
        "direction": "lower_is_better",
        "improvement_threshold": 0.01,
        "regression_threshold": 0.01,
        "unit": "ratio",
    },
    "episode_length_mean_steps": {
        "direction": "lower_is_better",
        "improvement_threshold": 5.0,
        "regression_threshold": 5.0,
        "unit": "steps",
    },
    "completion_time_mean_s": {
        "direction": "lower_is_better",
        "improvement_threshold": 0.01,
        "regression_threshold": 0.01,
        "unit": "seconds",
    },
}

DEFAULT_MIN_PAIRS = 10
DEFAULT_CONFIDENCE = 0.95


@dataclass
class PairedScenario:
    """Per-scenario evidence for both experiments (a = baseline, b = candidate)."""

    scenario_id: str
    a_success: bool
    b_success: bool
    a_return: float
    b_return: float
    a_steps: float
    b_steps: float
    a_collision: float
    b_collision: float
    a_completion_s: float | None = None
    b_completion_s: float | None = None
    a_infrastructure_failure: bool = False
    b_infrastructure_failure: bool = False


@dataclass
class ComparisonConfig:
    thresholds: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_THRESHOLDS.items()}
    )
    min_pairs: int = DEFAULT_MIN_PAIRS
    confidence: float = DEFAULT_CONFIDENCE
    n_resamples: int = 10_000
    seed: int = 12345


def _verdict(
    *,
    delta: float | None,
    ci: Interval,
    direction: str,
    improvement_threshold: float,
    regression_threshold: float,
    n_pairs: int,
    min_pairs: int,
) -> tuple[str, str]:
    if delta is None or ci.low is None or ci.high is None:
        return "MISSING", "no comparable data"
    if n_pairs < min_pairs:
        return (
            "INCONCLUSIVE",
            f"only {n_pairs} paired scenarios; below minimum {min_pairs} for a verdict",
        )

    excludes_zero = ci.low > 0.0 or ci.high < 0.0
    if direction == "neutral":
        status = (
            "IMPROVED" if excludes_zero and abs(delta) > regression_threshold else "INCONCLUSIVE"
        )
        return status, "neutral metric; large supported change only"

    # "better" means higher for higher_is_better, lower otherwise.
    better = delta > 0 if direction == "higher_is_better" else delta < 0
    magnitude = abs(delta)

    if not excludes_zero:
        return "INCONCLUSIVE", "95% interval includes zero (change not distinguishable from noise)"

    if better:
        if magnitude >= improvement_threshold:
            return "IMPROVED", f"supported improvement of {magnitude:.4g}"
        return "INCONCLUSIVE", "supported but below improvement threshold"

    # worse direction
    if magnitude >= regression_threshold:
        return "REGRESSED", f"supported regression of {magnitude:.4g}"
    return "INCONCLUSIVE", "supported but below regression threshold"


def build_report(
    pairs: list[PairedScenario],
    *,
    config: ComparisonConfig | None = None,
) -> Report:
    """Build a full comparison report from paired scenario evidence."""
    config = config or ComparisonConfig()
    report = Report()

    # Exclude pairs where either side was an infrastructure failure: those are
    # not evidence about policy quality.
    usable = [p for p in pairs if not p.a_infrastructure_failure and not p.b_infrastructure_failure]
    excluded = len(pairs) - len(usable)
    if excluded:
        report.warnings.append(
            f"{excluded} scenario(s) excluded from comparison due to infrastructure failures"
        )

    n = len(usable)
    if n == 0:
        report.warnings.append("no comparable scenarios after exclusions")
        report.summary = "Insufficient evidence: no comparable scenarios."
        return report

    if n < config.min_pairs:
        report.warnings.append(
            f"only {n} paired scenarios; below the minimum of {config.min_pairs} "
            "required for an improvement/regression verdict"
        )

    a_success = np.array([p.a_success for p in usable], dtype=bool)
    b_success = np.array([p.b_success for p in usable], dtype=bool)
    a_rate = float(a_success.mean())
    b_rate = float(b_success.mean())
    success_ci = paired_bootstrap_interval(
        a_success.astype(float),
        b_success.astype(float),
        confidence=config.confidence,
        n_resamples=config.n_resamples,
        seed=config.seed,
    )
    a_wilson = wilson_interval(int(a_success.sum()), n, config.confidence)
    b_wilson = wilson_interval(int(b_success.sum()), n, config.confidence)

    # success_rate (paired)
    cfg = config.thresholds["success_rate"]
    verdict, reason = _verdict(
        delta=b_rate - a_rate,
        ci=success_ci,
        direction=cfg["direction"],
        improvement_threshold=cfg["improvement_threshold"],
        regression_threshold=cfg["regression_threshold"],
        n_pairs=n,
        min_pairs=config.min_pairs,
    )
    report.metrics.append(
        MetricComparison(
            metric="success_rate",
            unit=cfg["unit"],
            direction=cfg["direction"],
            a=a_rate,
            b=b_rate,
            delta=b_rate - a_rate,
            relative=_relative(b_rate, a_rate),
            ci_low=success_ci.low,
            ci_high=success_ci.high,
            confidence=config.confidence,
            method="paired_bootstrap (wilson per-arm reported separately)",
            n_pairs=n,
            verdict=verdict,
            reason=reason,
        )
    )
    # Store per-arm CIs as auxiliary metrics for transparency.
    report.metrics.append(_aux_interval_metric("success_rate_a", a_wilson, cfg))
    report.metrics.append(_aux_interval_metric("success_rate_b", b_wilson, cfg))

    # Continuous paired metrics.
    report.metrics.append(_continuous_metric("return_mean", usable, "a_return", "b_return", config))
    report.metrics.append(
        _continuous_metric("episode_length_mean_steps", usable, "a_steps", "b_steps", config)
    )
    report.metrics.append(
        _continuous_metric("collision_rate", usable, "a_collision", "b_collision", config)
    )

    # completion_time is only defined for successes; pair on scenarios where both
    # succeeded so the comparison is like-for-like.
    both_succeeded = [p for p in usable if p.a_success and p.b_success]
    if both_succeeded:
        ct_pairs = [
            PairedScenario(
                scenario_id=p.scenario_id,
                a_success=p.a_success,
                b_success=p.b_success,
                a_return=p.a_return,
                b_return=p.b_return,
                a_steps=p.a_completion_s if p.a_completion_s is not None else p.a_steps,
                b_steps=p.b_completion_s if p.b_completion_s is not None else p.b_steps,
                a_collision=p.a_collision,
                b_collision=p.b_collision,
            )
            for p in both_succeeded
        ]
        report.metrics.append(
            _continuous_metric("completion_time_mean_s", ct_pairs, "a_steps", "b_steps", config)
        )
    else:
        report.metrics.append(
            MetricComparison(
                metric="completion_time_mean_s",
                unit=config.thresholds["completion_time_mean_s"]["unit"],
                direction="lower_is_better",
                a=None,
                b=None,
                delta=None,
                relative=None,
                ci_low=None,
                ci_high=None,
                confidence=config.confidence,
                method="paired_bootstrap",
                n_pairs=0,
                verdict="MISSING",
                reason="no scenarios where both policies succeeded",
            )
        )

    # Overall evidence verdict.
    primary = [m for m in report.metrics if m.metric in {"success_rate", "return_mean"}]
    any_improved = any(m.verdict == "IMPROVED" for m in report.metrics)
    any_regressed = any(m.verdict == "REGRESSED" for m in report.metrics)
    report.sufficient_evidence = n >= config.min_pairs
    report.summary = _summarize(report, n, any_improved, any_regressed, primary)
    return report


def _continuous_metric(
    name: str, pairs: list[PairedScenario], a_field: str, b_field: str, config: ComparisonConfig
) -> MetricComparison:
    cfg = config.thresholds[name]
    a = np.array([getattr(p, a_field) for p in pairs], dtype=float)
    b = np.array([getattr(p, b_field) for p in pairs], dtype=float)
    ci = paired_bootstrap_interval(
        a,
        b,
        confidence=config.confidence,
        n_resamples=config.n_resamples,
        seed=config.seed,
    )
    a_mean = float(a.mean()) if a.size else None
    b_mean = float(b.mean()) if b.size else None
    delta = float(b.mean() - a.mean()) if a.size else None
    verdict, reason = _verdict(
        delta=delta,
        ci=ci,
        direction=cfg["direction"],
        improvement_threshold=cfg["improvement_threshold"],
        regression_threshold=cfg["regression_threshold"],
        n_pairs=a.size,
        min_pairs=config.min_pairs,
    )
    return MetricComparison(
        metric=name,
        unit=cfg["unit"],
        direction=cfg["direction"],
        a=a_mean,
        b=b_mean,
        delta=delta,
        relative=_relative(b_mean, a_mean),
        ci_low=ci.low,
        ci_high=ci.high,
        confidence=config.confidence,
        method="paired_bootstrap",
        n_pairs=int(a.size),
        verdict=verdict,
        reason=reason,
    )


def _aux_interval_metric(name: str, interval: Interval, cfg: dict[str, Any]) -> MetricComparison:
    return MetricComparison(
        metric=name,
        unit=cfg["unit"],
        direction=cfg["direction"],
        a=interval.estimate,
        b=None,
        delta=None,
        relative=None,
        ci_low=interval.low,
        ci_high=interval.high,
        confidence=interval.confidence,
        method=interval.method,
        n_pairs=0,
        verdict="MISSING",
        reason="per-arm confidence interval (auxiliary)",
    )


def _relative(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base == 0:
        return None
    return (value - base) / abs(base)


def _summarize(
    report: Report,
    n: int,
    any_improved: bool,
    any_regressed: bool,
    primary: list[MetricComparison],
) -> str:
    if n == 0:
        return "Insufficient evidence: no comparable scenarios."
    if not report.sufficient_evidence:
        return (
            f"Inconclusive: only {n} paired scenarios. Report point estimates as "
            "descriptive only; no improvement/regression claim is supported."
        )
    parts = []
    if any_improved:
        parts.append("at least one metric improved with statistical support")
    if any_regressed:
        parts.append("at least one metric regressed with statistical support")
    if not parts:
        parts.append("no metric changed beyond thresholds with statistical support")
    return f"Across {n} paired scenarios: " + "; ".join(parts) + "."


__all__ = [
    "DEFAULT_MIN_PAIRS",
    "DEFAULT_THRESHOLDS",
    "ComparisonConfig",
    "PairedScenario",
    "build_report",
]
