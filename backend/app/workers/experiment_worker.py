"""Bounded local experiment worker.

Design:

* A single worker thread services a FIFO queue of experiment ids.
* Experiments can also be dispatched immediately via ``submit``.
* Concurrency is bounded: at most ``max_concurrent_experiments`` experiments run
  at once (default 1). This is a local worker by design; no Ray/Kafka/K8s.
* On startup, ``recover_interrupted`` requeues experiments left in RUNNING from a
  previous process, so a dead worker never leaves a job "running forever".
* Cancellation is cooperative: the experiment's ``cancellation_requested`` flag is
  checked between episodes; the worker stops and marks the experiment CANCELLED.
* Episode execution uses the real :func:`simulation.runners.episode_runner.run_episode`.
"""

from __future__ import annotations

import queue
import threading
import traceback
from typing import Any

from sqlalchemy import select

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.db.session import session_scope, utcnow
from backend.app.models.entities import Episode, Experiment
from backend.app.services import experiment_service as svc
from backend.app.services.state_machine import ExperimentStatus
from simulation.artifacts.store import LocalArtifactStore
from simulation.environments.reach_task import DEFAULT_REACH_SPEC
from simulation.runners.episode_runner import EpisodeConfig, run_episode

log = get_logger("simeval.worker")


class ExperimentWorker:
    """A bounded, single-threaded local experiment executor."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._current: str | None = None
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="simeval-worker", daemon=True)
            self._thread.start()
            self._running = True
        log.info("worker started")

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop.set()
            self._queue.put("")  # wake the loop
            thread = self._thread
            self._running = False
        if thread is not None:
            thread.join(timeout=timeout)
        log.info("worker stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_experiment(self) -> str | None:
        return self._current

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "current_experiment": self._current,
            "queue_depth": self.queue_depth,
            "max_concurrent_experiments": self.settings.max_concurrent_experiments,
        }

    def submit(self, experiment_id: str) -> None:
        self._queue.put(experiment_id)

    # ---------------------------------------------------------------- recovery
    def recover_interrupted(self) -> list[str]:
        """Requeue experiments left RUNNING by a prior process."""
        recovered: list[str] = []
        with session_scope() as session:
            rows = (
                session.execute(
                    select(Experiment).where(Experiment.status == ExperimentStatus.RUNNING.value)
                )
                .scalars()
                .all()
            )
            for row in rows:
                if row.cancellation_requested:
                    row.status = ExperimentStatus.CANCELLED.value
                    row.completed_at = utcnow()
                    row.error = "cancelled before worker restart"
                else:
                    row.status = ExperimentStatus.QUEUED.value
                    row.started_at = None
                    row.error = "requeued after worker restart"
                    recovered.append(row.experiment_id)
        for eid in recovered:
            self.submit(eid)
        if recovered:
            log.info("recovered %d interrupted experiment(s)", len(recovered))
        return recovered

    # -------------------------------------------------------------------- loop
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                experiment_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if not experiment_id or self._stop.is_set():
                break
            try:
                self._run_experiment(experiment_id)
            except Exception:
                log.error(
                    "unhandled worker error for experiment=%s\n%s",
                    experiment_id,
                    traceback.format_exc(),
                )
            finally:
                self._queue.task_done()
        with self._lock:
            self._running = False

    # ---------------------------------------------------------------- execute
    def _run_experiment(self, experiment_id: str) -> None:
        with self._lock:
            self._current = experiment_id
        try:
            with session_scope() as session:
                experiment = svc.get_experiment(session, experiment_id)
                if experiment is None:
                    log.warning("experiment not found experiment=%s", experiment_id)
                    return
                if experiment.cancellation_requested:
                    svc.transition(session, experiment, ExperimentStatus.CANCELLED)
                    return
                svc.transition(session, experiment, ExperimentStatus.RUNNING)
                log.info("experiment started experiment=%s", experiment_id)

            suite_data = None
            with session_scope() as session:
                experiment = svc.get_experiment(session, experiment_id)
                assert experiment is not None
                suite_data = svc.get_suite_data(
                    session, experiment.suite_name, experiment.suite_version
                )
                policy_name = experiment.policy_name
                policy_config = experiment.policy_config
                split = experiment.split
                eval_config = experiment.eval_config
                task_name = experiment.task_name
                task_version = experiment.task_version
                suite_hash = experiment.suite_hash

            if suite_data is None:
                self._fail(experiment_id, "scenario suite no longer available")
                return

            scenarios = (
                suite_data.scenarios if split == "all" else suite_data.by_split(split)  # type: ignore[arg-type]
            )
            if not scenarios:
                self._fail(experiment_id, f"no scenarios in split {split!r}")
                return

            store = LocalArtifactStore(self.settings.artifact_root)
            episode_config = EpisodeConfig(
                capture_every=eval_config.get("capture_every", 1),
                persist_artifacts=eval_config.get("persist_artifacts", True),
                timeout_s=eval_config.get("timeout_s"),
                policy_config=policy_config,
            )

            cancelled = False
            for scenario in scenarios:
                if self._is_cancelled(experiment_id):
                    cancelled = True
                    break
                episode = run_episode(
                    scenario=scenario,
                    policy_name=policy_name,
                    spec=DEFAULT_REACH_SPEC,
                    config=episode_config,
                    store=store,
                    experiment_id=experiment_id,
                )
                self._persist_episode(episode)

            if cancelled:
                with session_scope() as session:
                    experiment = svc.get_experiment(session, experiment_id)
                    assert experiment is not None
                    svc.transition(session, experiment, ExperimentStatus.CANCELLED)
                log.info("experiment cancelled experiment=%s", experiment_id)
                return

            with session_scope() as session:
                experiment = svc.get_experiment(session, experiment_id)
                assert experiment is not None
                experiment.metrics = svc.experiment_metrics(session, experiment_id)
                experiment.runtime_metadata = {
                    **experiment.runtime_metadata,
                    "suite_hash": suite_hash,
                    "n_scenarios": len(scenarios),
                    "task": f"{task_name} {task_version}",
                }
                svc.transition(session, experiment, ExperimentStatus.COMPLETED)
            log.info("experiment completed experiment=%s", experiment_id)
        finally:
            with self._lock:
                self._current = None

    def _is_cancelled(self, experiment_id: str) -> bool:
        with session_scope() as session:
            experiment = svc.get_experiment(session, experiment_id)
            return bool(experiment and experiment.cancellation_requested)

    def _persist_episode(self, episode) -> None:
        with session_scope() as session:
            row = Episode(
                episode_id=episode.episode_id,
                experiment_id=episode.experiment_id,
                scenario_id=episode.scenario_id,
                policy_name=episode.policy_name,
                policy_version=episode.policy_version,
                task_name=episode.task_name,
                task_version=episode.task_version,
                seed=episode.seed,
                split=episode.split,
                difficulty=episode.difficulty,
                success=episode.success,
                outcome=episode.outcome,
                failure_category=episode.failure_category,
                explanation=episode.explanation,
                rule=episode.rule,
                steps=episode.steps,
                wall_clock_s=episode.wall_clock_s,
                sim_time_s=episode.sim_time_s,
                return_sum=episode.return_sum,
                initial_ee_target_dist_m=_nan_safe(episode.initial_ee_target_dist_m),
                final_ee_target_dist_m=_nan_safe(episode.final_ee_target_dist_m),
                min_ee_target_dist_m=_nan_safe(episode.min_ee_target_dist_m),
                collision_steps=episode.collision_steps,
                max_collision_count=episode.max_collision_count,
                policy_inference_s=episode.policy_inference_s,
                metrics=episode.metrics,
                artifact_ref=episode.artifact_ref,
                error=episode.error,
            )
            session.add(row)

    def _fail(self, experiment_id: str, message: str) -> None:
        with session_scope() as session:
            experiment = svc.get_experiment(session, experiment_id)
            if experiment is not None:
                experiment.error = message
                svc.transition(session, experiment, ExperimentStatus.FAILED)
        log.error("experiment failed experiment=%s reason=%s", experiment_id, message)


def _nan_safe(value: float) -> float:
    import math

    return float(value) if value is not None and math.isfinite(float(value)) else 0.0


#: Process-wide worker instance used by the API.
_worker: ExperimentWorker | None = None


def get_worker() -> ExperimentWorker:
    global _worker
    if _worker is None:
        _worker = ExperimentWorker()
    return _worker


def reset_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
    _worker = None


__all__ = ["ExperimentWorker", "get_worker", "reset_worker"]
