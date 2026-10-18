#!/usr/bin/env python3
"""Milestone 2 demonstration: evaluate both policies on one seeded suite.

This script is the manual integration check for Milestone 2. It generates a
versioned scenario suite, runs both policies against the *same* scenarios, and
prints per-difficulty success counts. It does NOT persist results or compute the
full metric set; those arrive in Milestone 3.

Every number printed is produced by real MuJoCo rollouts. Nothing is mocked.

Usage:
    python scripts/demo_m2.py
    python scripts/demo_m2.py --n 30 --split held_out --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.environments.reach_env import ReachEnv
from simulation.policies.registry import (
    BASELINE_POLICY_NAME,
    CANDIDATE_POLICY_NAME,
    build_policy,
)
from simulation.scenarios.generator import Split, generate_suite


def evaluate(policy_name: str, suite, split: Split | None) -> dict:
    scenarios = suite.scenarios if split is None else suite.by_split(split)
    outcomes = []
    for sc in scenarios:
        env = ReachEnv()
        try:
            env.set_target(np.array(sc.target_position, dtype=float))
            obs = env.reset(
                seed=sc.seed,
                initial_qpos=sc.initial_qpos,
                qpos_noise=sc.qpos_noise,
            )
            policy = build_policy(policy_name, {}, env.kinematics_context())
            policy.reset()
            success = False
            steps = 0
            for i in range(env.spec.max_steps):
                result = env.step(policy.act(obs))
                obs = result.observation
                steps = i + 1
                if result.terminated:
                    success = True
                    break
            outcomes.append(
                {
                    "scenario_id": sc.scenario_id,
                    "difficulty": sc.difficulty,
                    "split": sc.split,
                    "success": success,
                    "steps": steps,
                    "final_distance_m": round(env.ee_target_distance(), 4),
                }
            )
        finally:
            env.close()
    by_difficulty: dict[str, dict[str, int]] = {}
    for o in outcomes:
        tier = by_difficulty.setdefault(o["difficulty"], {"success": 0, "failure": 0})
        tier["success" if o["success"] else "failure"] += 1
    return {
        "policy": policy_name,
        "n_scenarios": len(scenarios),
        "successes": sum(o["success"] for o in outcomes),
        "by_difficulty": by_difficulty,
        "outcomes": outcomes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Milestone 2 policy/suite demo")
    parser.add_argument("--n", type=int, default=30, help="number of scenarios")
    parser.add_argument(
        "--split",
        choices=["all", "dev", "validation", "held_out"],
        default="all",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    suite = generate_suite(n_scenarios=args.n)
    split: Split | None = None if args.split == "all" else args.split  # type: ignore[assignment]

    baseline = evaluate(BASELINE_POLICY_NAME, suite, split)
    candidate = evaluate(CANDIDATE_POLICY_NAME, suite, split)

    payload = {
        "suite": {
            "name": suite.suite_name,
            "version": suite.suite_version,
            "hash": suite.content_hash(),
            "counts": suite.counts(),
        },
        "split": args.split,
        "baseline": baseline,
        "candidate": candidate,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print("=" * 68)
    print("SimEval Milestone 2 demo — real rollouts, no mocks")
    print("=" * 68)
    print(
        f"suite {suite.suite_name} {suite.suite_version}  "
        f"hash={suite.content_hash()}  counts={suite.counts()}"
    )
    print(f"split: {args.split}")
    print("-" * 68)
    for label, res in (("baseline", baseline), ("candidate", candidate)):
        n, k = res["n_scenarios"], res["successes"]
        rate = (k / n) if n else 0.0
        print(f"{label:10s} {res['policy']:24s} success {k}/{n} ({rate:.1%})")
        for tier in sorted(res["by_difficulty"]):
            tier_counts = res["by_difficulty"][tier]
            ok = tier_counts.get("success", 0)
            no = tier_counts.get("failure", 0)
            print(f"    {tier:7s} {ok}/{ok + no}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
