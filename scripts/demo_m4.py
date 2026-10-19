#!/usr/bin/env python3
"""Milestone 4 demonstration: the full experiment API lifecycle.

Creates a suite, runs two policies through the API, waits for completion, then
prints persisted metrics, a comparison, an artifact inspection, and a
reproduction. Uses FastAPI's TestClient in-process (no network), but exercises
the real DB, worker, simulator, and artifact store.

Usage:
    python scripts/demo_m4.py
    python scripts/demo_m4.py --n 6 --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Use an isolated temp DB + artifact dir for the demo.
_TMP = tempfile.mkdtemp(prefix="simeval-demo-m4-")
os.environ.setdefault("SIMEVAL_DATABASE_URL", f"sqlite:///{_TMP}/demo.db")
os.environ.setdefault("SIMEVAL_ARTIFACT_ROOT", f"{_TMP}/artifacts")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def _wait(client: TestClient, eid: str, timeout_s: float = 120.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = client.get(f"/api/v1/experiments/{eid}").json()
        if payload["status"] in TERMINAL:
            return payload
        time.sleep(0.25)
    raise SystemExit(f"experiment {eid} timed out")


def run(n: int) -> dict:
    with TestClient(app) as client:
        suite = client.post(
            "/api/v1/scenario-suites",
            json={"suite_name": "demo-m4", "suite_version": "v1", "n_scenarios": n},
        ).json()
        runs = {}
        for policy in ("ik_planner_baseline", "resolved_rate_candidate"):
            created = client.post(
                "/api/v1/experiments",
                json={
                    "name": f"demo {policy}",
                    "policy_name": policy,
                    "suite_name": "demo-m4",
                    "suite_version": "v1",
                    "split": "all",
                    "capture_every": 5,
                },
            ).json()
            client.post(f"/api/v1/experiments/{created['experiment_id']}/start")
            finished = _wait(client, created["experiment_id"])
            episodes = client.get(f"/api/v1/experiments/{created['experiment_id']}/episodes").json()
            runs[policy] = {"experiment": finished, "episodes": episodes}

        a = runs["ik_planner_baseline"]["experiment"]["experiment_id"]
        b = runs["resolved_rate_candidate"]["experiment"]["experiment_id"]
        comparison = client.get("/api/v1/experiments/compare", params={"a": a, "b": b}).json()

        first_ep = runs["ik_planner_baseline"]["episodes"][0]
        artifacts = client.get(f"/api/v1/episodes/{first_ep['episode_id']}/artifacts").json()
        repro = client.post(f"/api/v1/experiments/{a}/reproduce").json()
        _wait(client, repro["experiment"]["experiment_id"])

    return {
        "suite": {"name": suite["suite_name"], "hash": suite["content_hash"]},
        "runs": {
            k: {
                "experiment_id": v["experiment"]["experiment_id"],
                "status": v["experiment"]["status"],
                "metrics": v["experiment"]["metrics"],
                "n_episodes": len(v["episodes"]),
            }
            for k, v in runs.items()
        },
        "comparison": comparison,
        "first_episode": first_ep,
        "artifacts": artifacts,
        "reproduction": {
            "source": repro["source_experiment_id"],
            "new": repro["experiment"]["experiment_id"],
            "suite_hash": repro["experiment"]["suite_hash"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Milestone 4 API demo")
    parser.add_argument("--n", type=int, default=6)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run(args.n)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return 0

    print("=" * 70)
    print("SimEval Milestone 4 demo — experiment API lifecycle (real worker + sim)")
    print("=" * 70)
    print(f"suite {result['suite']['name']} hash={result['suite']['hash']}")
    print("-" * 70)
    for policy, run_data in result["runs"].items():
        m = run_data["metrics"]
        print(
            f"{policy:24s} status={run_data['status']:9s} "
            f"episodes={run_data['n_episodes']} "
            f"success={m.get('n_success')}/{m.get('n_episodes_evaluated')}"
        )
    print("-" * 70)
    cmp = result["comparison"]
    print(f"comparison compatible={cmp['compatible']} shared={cmp['shared_scenarios']}")
    for metric in cmp["metrics"]:
        a = _fmt(metric["a"])
        b = _fmt(metric["b"])
        d = _fmt(metric["delta"])
        print(f"  {metric['metric']:28s} a={a} b={b} delta={d}")
    if cmp["warnings"]:
        for w in cmp["warnings"]:
            print(f"  ! {w}")
    print("-" * 70)
    ep = result["first_episode"]
    print(
        f"episode {ep['episode_id']} outcome={ep['outcome']} "
        f"final_dist={ep['final_ee_target_dist_m']:.4f} m"
    )
    print(
        f"artifacts exists={result['artifacts']['exists']} "
        f"arrays={sorted(result['artifacts']['arrays'])}"
    )
    print(
        f"reproduction {result['reproduction']['new']} "
        f"from {result['reproduction']['source']} "
        f"hash_match={result['reproduction']['suite_hash'] == result['suite']['hash']}"
    )
    print("=" * 70)
    return 0


def _fmt(value) -> str:
    return "n/a" if value is None else f"{value:.4f}"


if __name__ == "__main__":
    raise SystemExit(main())
