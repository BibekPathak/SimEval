"""Worker lifecycle tests (recovery, queue, cancellation)."""

from __future__ import annotations

from backend.app.db.session import session_scope
from backend.app.services import experiment_service as svc
from backend.app.services.state_machine import ExperimentStatus
from backend.app.workers.experiment_worker import ExperimentWorker


def test_worker_status_shape() -> None:
    w = ExperimentWorker()
    status = w.status()
    assert status["running"] is False
    assert status["queue_depth"] == 0
    assert status["current_experiment"] is None


def test_worker_start_stop() -> None:
    w = ExperimentWorker()
    w.start()
    assert w.is_running is True
    w.stop()
    assert w.is_running is False


def test_recover_requeues_running_experiment(client) -> None:
    client.post(
        "/api/v1/scenario-suites",
        json={"suite_name": "srecov", "suite_version": "v1", "n_scenarios": 3},
    )
    created = client.post(
        "/api/v1/experiments",
        json={
            "name": "recov",
            "policy_name": "ik_planner_baseline",
            "suite_name": "srecov",
            "suite_version": "v1",
        },
    ).json()
    eid = created["experiment_id"]

    # Simulate a worker that died while RUNNING.
    with session_scope() as session:
        row = svc.get_experiment(session, eid)
        assert row is not None
        row.status = ExperimentStatus.RUNNING.value

    worker = ExperimentWorker()
    recovered = worker.recover_interrupted()
    assert eid in recovered

    with session_scope() as session:
        row = svc.get_experiment(session, eid)
        assert row is not None
        assert row.status == ExperimentStatus.QUEUED.value
        assert row.started_at is None


def test_recover_cancels_flagged_running(client) -> None:
    client.post(
        "/api/v1/scenario-suites",
        json={"suite_name": "srecov2", "suite_version": "v1", "n_scenarios": 2},
    )
    created = client.post(
        "/api/v1/experiments",
        json={
            "name": "recov2",
            "policy_name": "ik_planner_baseline",
            "suite_name": "srecov2",
            "suite_version": "v1",
        },
    ).json()
    eid = created["experiment_id"]

    with session_scope() as session:
        row = svc.get_experiment(session, eid)
        assert row is not None
        row.status = ExperimentStatus.RUNNING.value
        row.cancellation_requested = True

    worker = ExperimentWorker()
    recovered = worker.recover_interrupted()
    assert eid not in recovered
    with session_scope() as session:
        row = svc.get_experiment(session, eid)
        assert row is not None
        assert row.status == ExperimentStatus.CANCELLED.value
