"""API integration tests via FastAPI TestClient.

These exercise the real app (real DB session, real worker, real MuJoCo
episodes). They are intentionally end-to-end.
"""

from __future__ import annotations

import time
from typing import Any

TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


def _wait(client, experiment_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = client.get(f"/api/v1/experiments/{experiment_id}").json()
        if payload["status"] in TERMINAL:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"experiment {experiment_id} did not finish in {timeout_s}s")


def _make_suite(client, name: str = "api-suite", n: int = 6) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/scenario-suites",
        json={"suite_name": name, "suite_version": "v1", "n_scenarios": n},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_experiment(client, suite_name: str, policy: str = "ik_planner_baseline", **extra):
    body = {
        "name": f"run-{policy}",
        "policy_name": policy,
        "suite_name": suite_name,
        "suite_version": "v1",
        "split": "all",
        "capture_every": 5,
        **extra,
    }
    resp = client.post("/api/v1/experiments", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ------------------------------------------------------------------ health etc
def test_health(client) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert "worker" in body


def test_tasks_listed(client) -> None:
    resp = client.get("/api/v1/tasks")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert "reach" in names


def test_policies_listed(client) -> None:
    resp = client.get("/api/v1/policies")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert {"ik_planner_baseline", "resolved_rate_candidate"} <= names


# ---------------------------------------------------------------------- suites
def test_create_and_get_suite(client) -> None:
    suite = _make_suite(client, "sget", 8)
    assert suite["n_scenarios"] == 8
    assert sum(suite["counts"].values()) == 8
    got = client.get("/api/v1/scenario-suites/sget/v1")
    assert got.status_code == 200
    assert got.json()["content_hash"] == suite["content_hash"]


def test_duplicate_suite_same_hash_is_idempotent(client) -> None:
    first = _make_suite(client, "sdup", 5)
    second = _make_suite(client, "sdup", 5)
    assert first["content_hash"] == second["content_hash"]


def test_conflicting_suite_version_returns_409(client) -> None:
    _make_suite(client, "sconf", 5)
    resp = client.post(
        "/api/v1/scenario-suites",
        json={"suite_name": "sconf", "suite_version": "v1", "n_scenarios": 9},
    )
    assert resp.status_code == 409


def test_suite_not_found(client) -> None:
    assert client.get("/api/v1/scenario-suites/nope/v1").status_code == 404


def test_suite_create_validation(client) -> None:
    resp = client.post(
        "/api/v1/scenario-suites",
        json={"suite_name": "bad", "suite_version": "v1", "n_scenarios": 0},
    )
    assert resp.status_code == 422


# ----------------------------------------------------------------- experiments
def test_create_experiment_validates_bindings(client) -> None:
    resp = client.post(
        "/api/v1/experiments",
        json={
            "name": "x",
            "policy_name": "ik_planner_baseline",
            "suite_name": "missing-suite",
            "suite_version": "v1",
        },
    )
    assert resp.status_code == 422


def test_create_experiment_invalid_split(client) -> None:
    resp = client.post(
        "/api/v1/experiments",
        json={
            "name": "x",
            "policy_name": "ik_planner_baseline",
            "suite_name": "x",
            "suite_version": "v1",
            "split": "bogus",
        },
    )
    assert resp.status_code == 422


def test_full_experiment_lifecycle(client) -> None:
    _make_suite(client, "slife", 6)
    created = _make_experiment(client, "slife")
    assert created["status"] == "QUEUED"
    eid = created["experiment_id"]

    started = client.post(f"/api/v1/experiments/{eid}/start")
    assert started.status_code == 200

    finished = _wait(client, eid)
    assert finished["status"] == "COMPLETED"
    assert finished["metrics"]["n_episodes_evaluated"] == 6
    assert 0.0 <= finished["metrics"]["success_rate"] <= 1.0

    episodes = client.get(f"/api/v1/experiments/{eid}/episodes").json()
    assert len(episodes) == 6
    for ep in episodes:
        assert ep["experiment_id"] == eid
        assert ep["outcome"]
        assert ep["artifact_ref"]


def test_episode_artifacts_endpoint(client) -> None:
    _make_suite(client, "sart", 3)
    created = _make_experiment(client, "sart")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    episodes = client.get(f"/api/v1/experiments/{eid}/episodes").json()
    ep_id = episodes[0]["episode_id"]

    detail = client.get(f"/api/v1/episodes/{ep_id}")
    assert detail.status_code == 200
    assert detail.json()["episode_id"] == ep_id

    art = client.get(f"/api/v1/episodes/{ep_id}/artifacts")
    assert art.status_code == 200
    body = art.json()
    assert body["exists"] is True
    assert "qpos" in body["arrays"] and "action" in body["arrays"]


def test_unknown_episode_404(client) -> None:
    assert client.get("/api/v1/episodes/nope").status_code == 404
    assert client.get("/api/v1/episodes/nope/artifacts").status_code == 404
    assert client.get("/api/v1/episodes/nope/artifacts/series").status_code == 404


def test_episode_artifact_series(client) -> None:
    _make_suite(client, "sseries", 3)
    created = _make_experiment(client, "sseries", capture_every=1)
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    ep_id = client.get(f"/api/v1/experiments/{eid}/episodes").json()[0]["episode_id"]

    resp = client.get(f"/api/v1/episodes/{ep_id}/artifacts/series")
    assert resp.status_code == 200
    body = resp.json()
    assert body["exists"] is True
    assert body["n_steps"] > 0
    # Real recorded series, not shapes.
    assert "ee_target_dist" in body["series"]
    assert len(body["series"]["ee_target_dist"]) == body["returned_steps"]
    assert isinstance(body["series"]["qpos"][0], list)  # 2-D array -> list of rows
    # ee_target_dist is recorded with shape (T, 1), so it is nested lists.
    first = body["series"]["ee_target_dist"][0]
    assert isinstance(first, list) and isinstance(first[0], (int, float))


def test_episode_artifact_series_rejects_unknown_array(client) -> None:
    _make_suite(client, "sseries2", 2)
    created = _make_experiment(client, "sseries2")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    ep_id = client.get(f"/api/v1/experiments/{eid}/episodes").json()[0]["episode_id"]
    resp = client.get(f"/api/v1/episodes/{ep_id}/artifacts/series", params={"arrays": "bogus"})
    assert resp.status_code == 422


def test_episode_artifact_series_downsampling(client) -> None:
    _make_suite(client, "sseries3", 2)
    created = _make_experiment(client, "sseries3", capture_every=1)
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    ep_id = client.get(f"/api/v1/experiments/{eid}/episodes").json()[0]["episode_id"]
    body = client.get(f"/api/v1/episodes/{ep_id}/artifacts/series", params={"max_steps": 5}).json()
    assert body["returned_steps"] <= 5
    assert body["stride"] >= 1


def test_metrics_endpoint_matches_experiment(client) -> None:
    _make_suite(client, "smet", 4)
    created = _make_experiment(client, "smet")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    finished = _wait(client, eid)
    metrics = client.get(f"/api/v1/experiments/{eid}/metrics").json()
    assert metrics["n_episodes_evaluated"] == finished["metrics"]["n_episodes_evaluated"]


def test_start_completed_experiment_conflicts(client) -> None:
    _make_suite(client, "sstart", 2)
    created = _make_experiment(client, "sstart")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    again = client.post(f"/api/v1/experiments/{eid}/start")
    assert again.status_code == 409


def test_cancel_queued_experiment(client) -> None:
    _make_suite(client, "scancel", 3)
    created = _make_experiment(client, "scancel")
    eid = created["experiment_id"]
    resp = client.post(f"/api/v1/experiments/{eid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_cancel_completed_conflicts(client) -> None:
    _make_suite(client, "scancel2", 2)
    created = _make_experiment(client, "scancel2")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    assert client.post(f"/api/v1/experiments/{eid}/cancel").status_code == 409


def test_split_filter_reduces_episodes(client) -> None:
    suite = _make_suite(client, "ssplit", 12)
    created = _make_experiment(client, "ssplit", split="held_out")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    episodes = client.get(f"/api/v1/experiments/{eid}/episodes").json()
    assert len(episodes) == suite["counts"].get("held_out", 0)
    assert all(e["split"] == "held_out" for e in episodes)


def test_compare_requires_matching_settings(client) -> None:
    _make_suite(client, "scmp", 6)
    a = _make_experiment(client, "scmp", policy="ik_planner_baseline")
    b = _make_experiment(client, "scmp", policy="resolved_rate_candidate")
    for exp in (a, b):
        client.post(f"/api/v1/experiments/{exp['experiment_id']}/start")
        _wait(client, exp["experiment_id"])
    cmp = client.get(
        "/api/v1/experiments/compare",
        params={"a": a["experiment_id"], "b": b["experiment_id"]},
    ).json()
    assert cmp["compatible"] is True
    assert cmp["shared_scenarios"] == 6
    metric_names = {m["metric"] for m in cmp["metrics"]}
    assert {"success_rate", "episode_length_mean_steps"} <= metric_names
    # Milestone 5: point estimates carry intervals, verdicts, and an evidence flag.
    assert "sufficient_evidence" in cmp
    assert "summary" in cmp
    sr = next(m for m in cmp["metrics"] if m["metric"] == "success_rate")
    assert sr["verdict"] in {"IMPROVED", "REGRESSED", "INCONCLUSIVE", "MISSING"}
    assert sr["ci_low"] is not None and sr["ci_high"] is not None
    assert sr["ci_low"] <= sr["ci_high"]
    # 6 shared scenarios is below the default minimum for a verdict.
    assert cmp["sufficient_evidence"] is False
    assert any("below the minimum" in w for w in cmp["warnings"])


def test_compare_incompatible_experiments_warns(client) -> None:
    _make_suite(client, "scmp2", 6)
    _make_suite(client, "scmp3", 6)
    a = _make_experiment(client, "scmp2")
    b = _make_experiment(client, "scmp3")
    cmp = client.get(
        "/api/v1/experiments/compare",
        params={"a": a["experiment_id"], "b": b["experiment_id"]},
    ).json()
    assert cmp["compatible"] is False
    assert any("suite" in w for w in cmp["warnings"])


def test_reproduce_experiment(client) -> None:
    _make_suite(client, "srep", 4)
    created = _make_experiment(client, "srep")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    resp = client.post(f"/api/v1/experiments/{eid}/reproduce")
    assert resp.status_code == 201
    body = resp.json()
    assert body["source_experiment_id"] == eid
    repro = body["experiment"]
    assert repro["suite_hash"] == created["suite_hash"]
    assert repro["policy_config"] == created["policy_config"]
    _wait(client, repro["experiment_id"])
    original = client.get(f"/api/v1/experiments/{eid}").json()
    reproduced = client.get(f"/api/v1/experiments/{repro['experiment_id']}").json()
    assert original["metrics"]["n_success"] == reproduced["metrics"]["n_success"]


def test_experiment_persistence_across_restart(client, artifact_root) -> None:
    _make_suite(client, "spersist", 3)
    created = _make_experiment(client, "spersist")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    # A fresh TestClient triggers a new app lifespan (simulated restart).
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as fresh:
        got = fresh.get(f"/api/v1/experiments/{eid}").json()
        assert got["status"] == "COMPLETED"
        episodes = fresh.get(f"/api/v1/experiments/{eid}/episodes").json()
        assert len(episodes) == 3


def test_list_experiments_and_filter(client) -> None:
    _make_suite(client, "slist", 2)
    created = _make_experiment(client, "slist")
    eid = created["experiment_id"]
    client.post(f"/api/v1/experiments/{eid}/start")
    _wait(client, eid)
    completed = client.get("/api/v1/experiments", params={"status": "COMPLETED"}).json()
    assert any(e["experiment_id"] == eid for e in completed)
    bad = client.get("/api/v1/experiments", params={"status": "NOPE"})
    assert bad.status_code == 422


def test_compare_sufficient_evidence_on_large_suite(client) -> None:
    # 24 shared scenarios is above the default minimum of 10.
    _make_suite(client, "sbig", 24)
    a = _make_experiment(client, "sbig", policy="ik_planner_baseline")
    b = _make_experiment(client, "sbig", policy="resolved_rate_candidate")
    for exp in (a, b):
        client.post(f"/api/v1/experiments/{exp['experiment_id']}/start")
        _wait(client, exp["experiment_id"])
    cmp = client.get(
        "/api/v1/experiments/compare",
        params={"a": a["experiment_id"], "b": b["experiment_id"]},
    ).json()
    assert cmp["shared_scenarios"] == 24
    assert cmp["sufficient_evidence"] is True
