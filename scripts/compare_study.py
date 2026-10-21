#!/usr/bin/env python3
"""Reproducible multi-scenario comparison study.

Runs two policies across a large, versioned scenario suite on the held-out
split, then reports the full statistical comparison (point estimates, confidence
intervals, verdicts). This is the script behind the comparison numbers recorded
in ``docs/research-log.md`` and ``docs/evaluation-methodology.md``.

It is honest by construction: it prints whatever the statistics produce,
including INCONCLUSIVE verdicts and regressions.

Usage:
    python scripts/compare_study.py
    python scripts/compare_study.py --n 120 --split held_out --json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.artifacts.store import LocalArtifactStore
from simulation.metrics.comparison import (
    ComparisonConfig,
    PairedScenario,
    build_report,
)
from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.episode_runner import EpisodeConfig, run_episode
from simulation.runners.outcome import Outcome, is_infrastructure_failure
from simulation.scenarios.generator import generate_suite


def _run(policy: str, scenarios, timestep: float, store) -> dict[str, object]:
    per_scenario: dict[str, object] = {}
    episodes = []
    for sc in scenarios:
        ep = run_episode(
            scenario=sc,
            policy_name=policy,
            config=EpisodeConfig(capture_every=5, persist_artifacts=False),
            store=store,
            experiment_id="compare-study",
        )
        episodes.append(ep)
        per_scenario[sc.scenario_id] = ep
    metrics = compute_metrics(episodes, timestep_s=timestep)
    return {"episodes": per_scenario, "metrics": metrics, "all": episodes}


def main() -> int:
    parser = argparse.ArgumentParser(description="Reproducible multi-scenario comparison")
    parser.add_argument("--n", type=int, default=120)
    parser.add_argument("--base-seed", type=int, default=20000)
    parser.add_argument("--split", default="held_out")
    parser.add_argument("--a", default="ik_planner_baseline")
    parser.add_argument("--b", default="resolved_rate_candidate")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    suite = generate_suite(
        suite_name="compare-study", suite_version="v1", n_scenarios=args.n, base_seed=args.base_seed
    )
    scenarios = suite.scenarios if args.split == "all" else suite.by_split(args.split)  # type: ignore[arg-type]

    timestep = 0.005
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalArtifactStore(tmp)
        t0 = time.perf_counter()
        arm_a = _run(args.a, scenarios, timestep, store)
        arm_b = _run(args.b, scenarios, timestep, store)
        wall = time.perf_counter() - t0

    # Build scenario-paired evidence.
    pairs = []
    a_eps = arm_a["episodes"]
    b_eps = arm_b["episodes"]
    for sid in sorted(set(a_eps) & set(b_eps)):  # type: ignore[arg-type]
        ea = a_eps[sid]  # type: ignore[index]
        eb = b_eps[sid]  # type: ignore[index]
        pairs.append(
            PairedScenario(
                scenario_id=sid,
                a_success=ea.success,
                b_success=eb.success,
                a_return=ea.return_sum,
                b_return=eb.return_sum,
                a_steps=float(ea.steps),
                b_steps=float(eb.steps),
                a_collision=float(ea.collision_steps),
                b_collision=float(eb.collision_steps),
                a_completion_s=ea.steps * timestep,
                b_completion_s=eb.steps * timestep,
                a_infrastructure_failure=is_infrastructure_failure(Outcome(ea.outcome)),
                b_infrastructure_failure=is_infrastructure_failure(Outcome(eb.outcome)),
            )
        )

    report = build_report(pairs, config=ComparisonConfig())

    result = {
        "suite": {"name": suite.suite_name, "hash": suite.content_hash(), "counts": suite.counts()},
        "split": args.split,
        "n_scenarios": len(scenarios),
        "a": args.a,
        "b": args.b,
        "aggregate_a": arm_a["metrics"].to_dict(),  # type: ignore[union-attr]
        "aggregate_b": arm_b["metrics"].to_dict(),  # type: ignore[union-attr]
        "comparison": {
            "sufficient_evidence": report.sufficient_evidence,
            "summary": report.summary,
            "warnings": report.warnings,
            "metrics": [m.to_dict() for m in report.metrics],
        },
        "wall_clock_s": wall,
    }

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    ma = arm_a["metrics"]
    mb = arm_b["metrics"]
    print("=" * 76)
    print("SimEval reproducible comparison study")
    print("=" * 76)
    print(
        f"suite {suite.suite_name} hash={suite.content_hash()} split={args.split} n={len(scenarios)}"
    )
    print("-" * 76)
    print(
        f"A = {args.a:<28} success {ma.n_success}/{ma.n_episodes_evaluated} "
        f"({(ma.success_rate or 0) * 100:.1f}%)  len~{ma.episode_length_mean_steps:.1f}"
    )
    print(
        f"B = {args.b:<28} success {mb.n_success}/{mb.n_episodes_evaluated} "
        f"({(mb.success_rate or 0) * 100:.1f}%)  len~{mb.episode_length_mean_steps:.1f}"
    )
    print("-" * 76)
    print(f"evidence sufficient: {report.sufficient_evidence}")
    for m in report.metrics:
        if m.metric in {"success_rate_a", "success_rate_b"}:
            continue
        ci = "n/a" if m.ci_low is None else f"[{m.ci_low:.3f}, {m.ci_high:.3f}]"
        delta = "n/a" if m.delta is None else f"{m.delta:+.3f}"
        print(f"  {m.metric:<28} delta={delta:<10} ci={ci:<22} {m.verdict}")
    print(f"summary: {report.summary}")
    print(f"wall clock: {wall:.1f} s")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
