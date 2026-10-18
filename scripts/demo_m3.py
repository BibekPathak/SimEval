#!/usr/bin/env python3
"""Milestone 3 demonstration: run a suite, grade every episode, aggregate metrics.

This executes the full evaluation pipeline for one policy over a versioned
scenario suite:

  scenario -> episode runner -> trace recording -> artifact persistence
           -> grader -> aggregated metrics

Every number printed derives from persisted episode results. No value is mocked.

Usage:
    python scripts/demo_m3.py
    python scripts/demo_m3.py --n 24 --policy resolved_rate_candidate
    python scripts/demo_m3.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.artifacts.store import LocalArtifactStore
from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.episode_runner import EpisodeConfig, run_episode
from simulation.scenarios.generator import generate_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Milestone 3 evaluation demo")
    parser.add_argument("--n", type=int, default=24)
    parser.add_argument("--policy", default="ik_planner_baseline")
    parser.add_argument("--split", choices=["all", "dev", "validation", "held_out"], default="all")
    parser.add_argument("--capture-every", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    suite = generate_suite(n_scenarios=args.n)
    scenarios = suite.scenarios if args.split == "all" else suite.by_split(args.split)

    with tempfile.TemporaryDirectory() as tmp:
        store = LocalArtifactStore(tmp)
        episodes = [
            run_episode(
                scenario=sc,
                policy_name=args.policy,
                store=store,
                experiment_id="demo-m3",
                config=EpisodeConfig(capture_every=args.capture_every),
            )
            for sc in scenarios
        ]
        metrics = compute_metrics(episodes, timestep_s=0.005)
        # Verify one artifact round-trips from disk.
        ref = next((e.artifact_ref for e in episodes if e.artifact_ref), None)
        artifact_ok = bool(ref) and store.exists(ref) and bool(store.get_arrays(ref))

    payload = {
        "suite": {
            "name": suite.suite_name,
            "version": suite.suite_version,
            "hash": suite.content_hash(),
        },
        "split": args.split,
        "policy": args.policy,
        "metrics": metrics.to_dict(),
        "artifacts_persisted": artifact_ok,
        "outcome_counts": _outcome_counts(episodes),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    m = metrics
    print("=" * 70)
    print("SimEval Milestone 3 demo — run -> grade -> aggregate (real episodes)")
    print("=" * 70)
    print(f"suite {suite.suite_name} {suite.suite_version} hash={suite.content_hash()}")
    print(f"policy: {args.policy}   split: {args.split}   capture_every: {args.capture_every}")
    print("-" * 70)
    print(f"episodes total          : {m.n_episodes_total}")
    print(f"evaluated (in denominator): {m.n_episodes_evaluated}")
    print(f"infrastructure failures : {m.n_infrastructure_failures}")
    print(
        f"success                 : {m.n_success}/{m.n_episodes_evaluated}"
        f"  ({_pct(m.success_rate)})"
    )
    print(f"failure rate            : {_pct(m.failure_rate)}")
    print(f"completion time mean    : {_fmt(m.completion_time_mean_s)} s (successes only)")
    print(f"episode length mean     : {_fmt(m.episode_length_mean_steps)} steps")
    print(f"collision rate          : {_pct(m.collision_rate)}")
    print(f"return mean / median    : {_fmt(m.return_mean)} / {_fmt(m.return_median)}")
    print(f"throughput              : {_fmt(m.throughput_eps_per_s)} episodes/s")
    print(f"mean policy inference   : {_fmt(m.mean_policy_inference_ms)} ms/episode")
    print(f"failure categories      : {m.failure_categories or '{}'}")
    print(f"artifact round-trip ok  : {artifact_ok}")
    print("=" * 70)
    return 0


def _outcome_counts(episodes) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in episodes:
        counts[e.outcome] = counts.get(e.outcome, 0) + 1
    return counts


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


if __name__ == "__main__":
    raise SystemExit(main())
