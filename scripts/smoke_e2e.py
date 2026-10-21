#!/usr/bin/env python3
"""End-to-end smoke test for SimEval (Milestone 7).

Drives the complete evaluation workflow through the real API against the real
database, worker, and MuJoCo simulation, using an isolated temporary database
and artifact root. It is safe to run repeatedly and in CI.

Workflow verified:
  1. services report healthy;
  2. a versioned scenario suite is created;
  3. a baseline policy experiment runs to completion;
  4. a candidate policy experiment runs on the same scenarios;
  5. per-episode outcomes are persisted and retrievable;
  6. aggregate metrics and a statistical comparison are produced;
  7. a failed episode's evidence is inspectable;
  8. an experiment is reproduced from its saved configuration;
  9. results remain readable after an application restart (new app lifespan).

Exit code is non-zero if any step fails.

Usage:
    python scripts/smoke_e2e.py
    python scripts/smoke_e2e.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="simeval-e2e-")
os.environ.setdefault("SIMEVAL_DATABASE_URL", f"sqlite:///{_TMP}/e2e.db")
os.environ.setdefault("SIMEVAL_ARTIFACT_ROOT", f"{_TMP}/artifacts")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.main import app  # noqa: E402

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def _wait(client: TestClient, eid: str, timeout_s: float = 180.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = client.get(f"/api/v1/experiments/{eid}").json()
        if payload["status"] in TERMINAL:
            return payload
        time.sleep(0.25)
    raise SystemExit(f"experiment {eid} did not finish within {timeout_s}s")


def run(n_scenarios: int) -> dict:
    steps: list[dict] = []
    with TestClient(app) as client:
        health = client.get("/api/v1/health").json()
        _require(health["status"] == "ok", f"health is {health['status']}")
        steps.append({"step": "health", "ok": True, "detail": health["status"]})

        suite = client.post(
            "/api/v1/scenario-suites",
            json={"suite_name": "e2e", "suite_version": "v1", "n_scenarios": n_scenarios},
        ).json()
        _require(suite["n_scenarios"] == n_scenarios, "suite size mismatch")
        steps.append({"step": "create_suite", "ok": True, "detail": suite["content_hash"]})

        runs: dict[str, dict] = {}
        for policy in ("ik_planner_baseline", "resolved_rate_candidate"):
            created = client.post(
                "/api/v1/experiments",
                json={
                    "name": f"e2e {policy}",
                    "policy_name": policy,
                    "suite_name": "e2e",
                    "suite_version": "v1",
                    "split": "all",
                    "capture_every": 5,
                },
            ).json()
            client.post(f"/api/v1/experiments/{created['experiment_id']}/start")
            finished = _wait(client, created["experiment_id"])
            _require(finished["status"] == "COMPLETED", f"{policy} status {finished['status']}")
            episodes = client.get(
                f"/api/v1/experiments/{created['experiment_id']}/episodes",
                params={"limit": 500},
            ).json()
            _require(len(episodes) == n_scenarios, f"{policy} episode count mismatch")
            runs[policy] = {"experiment": finished, "episodes": episodes}
            steps.append(
                {
                    "step": f"run_{policy}",
                    "ok": True,
                    "detail": f"{finished['metrics'].get('n_success')}/{n_scenarios} success",
                }
            )

        a = runs["ik_planner_baseline"]["experiment"]["experiment_id"]
        b = runs["resolved_rate_candidate"]["experiment"]["experiment_id"]
        comparison = client.get("/api/v1/experiments/compare", params={"a": a, "b": b}).json()
        _require(comparison["compatible"] is True, "comparison reported incompatible")
        _require(comparison["shared_scenarios"] == n_scenarios, "shared scenario mismatch")
        steps.append(
            {
                "step": "compare",
                "ok": True,
                "detail": comparison["summary"],
            }
        )

        # Failed-episode evidence inspection (pick any non-success episode).
        evidence = None
        for ep in runs["ik_planner_baseline"]["episodes"]:
            if not ep["success"]:
                evidence = ep
                break
        if evidence is not None:
            detail = client.get(f"/api/v1/episodes/{evidence['episode_id']}").json()
            _require(detail["rule"] != "", "failed episode has no deciding rule")
            artifacts = client.get(f"/api/v1/episodes/{evidence['episode_id']}/artifacts").json()
            _require(artifacts["exists"] is True, "failed episode artifact missing")
            steps.append(
                {
                    "step": "inspect_failure",
                    "ok": True,
                    "detail": f"{detail['outcome']}: {detail['rule']}",
                }
            )
        else:
            steps.append(
                {"step": "inspect_failure", "ok": True, "detail": "no failures in this suite"}
            )

        repro = client.post(f"/api/v1/experiments/{a}/reproduce").json()
        resumed = _wait(client, repro["experiment"]["experiment_id"])
        original = client.get(f"/api/v1/experiments/{a}").json()
        _require(
            original["metrics"]["n_success"] == resumed["metrics"]["n_success"],
            "reproduction success count differs",
        )
        steps.append(
            {
                "step": "reproduce",
                "ok": True,
                "detail": f"{repro['experiment']['experiment_id']} matches original",
            }
        )

    # Restart: a fresh TestClient re-enters the app lifespan; results must persist.
    with TestClient(app) as fresh:
        persisted = fresh.get(f"/api/v1/experiments/{a}").json()
        _require(persisted["status"] == "COMPLETED", "result lost after restart")
        steps.append({"step": "restart_persistence", "ok": True, "detail": persisted["status"]})

    return {
        "ok": all(s["ok"] for s in steps),
        "n_scenarios": n_scenarios,
        "steps": steps,
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"E2E FAILED: {message}")


def main() -> int:
    parser = argparse.ArgumentParser(description="SimEval end-to-end smoke test")
    parser.add_argument("--n", type=int, default=8, help="scenarios per suite")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = run(args.n)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print("=" * 66)
        print("SimEval end-to-end smoke test")
        print("=" * 66)
        for step in result["steps"]:
            mark = "PASS" if step["ok"] else "FAIL"
            print(f"[{mark}] {step['step']:<20} {step['detail']}")
        print("=" * 66)
        print("E2E:", "OK" if result["ok"] else "FAILED")
        print("=" * 66)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
