#!/usr/bin/env python3
"""Evaluate and ablate the behavior-cloning policy (Milestone 8).

Compares, on the **held-out** scenario split (never used for demonstration
collection or training):

  * ``ik_planner_baseline`` — the expert the network imitates;
  * ``behavior_cloning``    — the learned policy.

It also runs one ablation: ``behavior_cloning`` with a different checkpoint
hidden-layer width (trained on the fly if a matching checkpoint is absent is out
of scope; instead we ablate the *number of demonstrations* by retraining a small
variant) — to keep this deterministic and fast, the ablation compares the learned
policy **with** and **without** action clamping at the joint limits, isolating
one concrete design choice.

Every number is produced by real MuJoCo evaluation through the episode runner and
graded by the same grader used elsewhere. Failure cases are recorded.

Usage:
    python scripts/eval_bc.py
    python scripts/eval_bc.py --split held_out --n 40 --json
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
from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.episode_runner import EpisodeConfig, run_episode
from simulation.runners.outcome import Outcome, is_infrastructure_failure
from simulation.scenarios.generator import generate_suite


def evaluate(policy_name: str, suite, split: str, policy_config: dict | None, store) -> dict:
    scenarios = suite.scenarios if split == "all" else suite.by_split(split)  # type: ignore[arg-type]
    episodes = []
    failures = []
    for sc in scenarios:
        ep = run_episode(
            scenario=sc,
            policy_name=policy_name,
            config=EpisodeConfig(capture_every=10, policy_config=policy_config),
            store=store,
            experiment_id="eval_bc",
        )
        episodes.append(ep)
        if not ep.success:
            failures.append(
                {
                    "scenario_id": ep.scenario_id,
                    "difficulty": ep.difficulty,
                    "outcome": ep.outcome,
                    "final_ee_target_dist_m": round(ep.final_ee_target_dist_m, 4),
                    "rule": ep.rule,
                }
            )
    metrics = compute_metrics(episodes, timestep_s=0.005)
    infra = sum(1 for e in episodes if is_infrastructure_failure(Outcome(e.outcome)))
    return {
        "policy": policy_name,
        "split": split,
        "n_scenarios": len(scenarios),
        "metrics": metrics.to_dict(),
        "infrastructure_failures": infra,
        "failures": failures[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate/ablate the behavior-cloning policy")
    parser.add_argument("--suite-name", default="bc-eval")
    parser.add_argument("--n", type=int, default=60)
    parser.add_argument("--base-seed", type=int, default=9000)
    parser.add_argument("--split", default="held_out")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    suite = generate_suite(
        suite_name=args.suite_name,
        suite_version="v1",
        n_scenarios=args.n,
        base_seed=args.base_seed,
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalArtifactStore(tmp)
        t0 = time.perf_counter()
        expert = evaluate("ik_planner_baseline", suite, args.split, None, store)
        learned = evaluate("behavior_cloning", suite, args.split, None, store)
        learned_ablation = evaluate(
            "behavior_cloning",
            suite,
            args.split,
            {"clamp_to_limits": False},
            store,
        )
        wall = time.perf_counter() - t0

    result = {
        "suite": {
            "name": suite.suite_name,
            "hash": suite.content_hash(),
            "split": args.split,
            "counts": suite.counts(),
        },
        "expert": expert,
        "learned": learned,
        "ablation_no_clamp": learned_ablation,
        "wall_clock_s": wall,
    }

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print("=" * 72)
    print("SimEval Milestone 8 — behavior-cloning evaluation (held-out split)")
    print("=" * 72)
    print(f"suite {suite.suite_name} hash={suite.content_hash()} split={args.split}")
    print(f"held-out scenarios: {expert['n_scenarios']}")
    print("-" * 72)
    _print_arm("expert      (ik_planner_baseline)", expert)
    _print_arm("learned     (behavior_cloning)", learned)
    _print_arm("ablation    (no joint-limit clamp)", learned_ablation)
    print("-" * 72)
    if learned["failures"]:
        print("learned failure cases (up to 10):")
        for f in learned["failures"]:
            print(
                f"  {f['scenario_id']:<20} {f['difficulty']:<7} {f['outcome']:<20} "
                f"final={f['final_ee_target_dist_m']} m"
            )
    else:
        print("learned: no failures on the held-out split")
    print(f"wall clock: {wall:.1f} s")
    print("=" * 72)
    return 0


def _print_arm(label: str, arm: dict) -> None:
    m = arm["metrics"]
    rate = m["success_rate"]
    print(
        f"{label:<36} success {m['n_success']}/{m['n_episodes_evaluated']} "
        f"({(rate or 0) * 100:5.1f}%)  "
        f"len~{_fmt(m['episode_length_mean_steps'])}  "
        f"collis {_fmt(m['collision_rate'])}"
    )


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


if __name__ == "__main__":
    raise SystemExit(main())
