"""Experiment service: create, query, transition, aggregate, compare, reproduce.

This layer owns the experiment lifecycle and persistence. It contains no
simulation logic; the worker calls into it, and the API calls into it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import utcnow
from backend.app.models.entities import Episode, Experiment, Policy, ScenarioSuite, Task
from backend.app.services.state_machine import (
    ExperimentStatus,
    assert_transition,
    coerce,
    is_terminal,
)
from simulation.metrics.comparison import (
    ComparisonConfig,
    PairedScenario,
    build_report,
)
from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.outcome import EpisodeResult
from simulation.scenarios.generator import ScenarioSuite as ScenarioSuiteData


class ExperimentError(RuntimeError):
    pass


@dataclass
class ExperimentCreateSpec:
    name: str
    policy_name: str
    suite_name: str
    suite_version: str
    task_name: str = "reach"
    task_version: str = "v1"
    split: str = "all"
    description: str | None = None
    policy_config: dict[str, Any] | None = None
    dataset_version: str | None = None
    seed: int | None = None
    capture_every: int = 1
    persist_artifacts: bool = True
    timeout_s: float | None = None
    code_revision: str | None = None
    runtime_metadata: dict[str, Any] | None = None


def _new_experiment_id() -> str:
    return f"exp_{uuid.uuid4().hex[:16]}"


def create_experiment(session: Session, spec: ExperimentCreateSpec) -> Experiment:
    """Create and persist a QUEUED experiment. Validates bindings exist."""
    task = session.execute(
        select(Task).where(Task.name == spec.task_name, Task.version == spec.task_version)
    ).scalar_one_or_none()
    if task is None:
        raise ExperimentError(f"unknown task {spec.task_name} {spec.task_version}")

    suite = session.execute(
        select(ScenarioSuite).where(
            ScenarioSuite.suite_name == spec.suite_name,
            ScenarioSuite.suite_version == spec.suite_version,
        )
    ).scalar_one_or_none()
    if suite is None:
        raise ExperimentError(f"unknown scenario suite {spec.suite_name} {spec.suite_version}")

    policy = (
        session.execute(
            select(Policy).where(Policy.name == spec.policy_name).order_by(Policy.id.desc())
        )
        .scalars()
        .first()
    )
    if policy is None:
        raise ExperimentError(f"unknown policy {spec.policy_name}")

    policy_config = spec.policy_config if spec.policy_config is not None else policy.default_config

    eval_config = {
        "capture_every": spec.capture_every,
        "persist_artifacts": spec.persist_artifacts,
        "timeout_s": spec.timeout_s,
        "split": spec.split,
    }
    experiment = Experiment(
        experiment_id=_new_experiment_id(),
        name=spec.name,
        description=spec.description,
        policy_name=policy.name,
        policy_version=policy.version,
        policy_config=policy_config,
        task_name=spec.task_name,
        task_version=spec.task_version,
        suite_name=spec.suite_name,
        suite_version=spec.suite_version,
        suite_hash=suite.content_hash,
        split=spec.split,
        dataset_version=spec.dataset_version,
        seeds={"experiment_seed": spec.seed},
        eval_config=eval_config,
        code_revision=spec.code_revision,
        runtime_metadata=spec.runtime_metadata or {},
        status=ExperimentStatus.QUEUED.value,
        created_at=utcnow(),
    )
    session.add(experiment)
    session.commit()
    session.refresh(experiment)
    return experiment


def get_experiment(session: Session, experiment_id: str) -> Experiment | None:
    return session.execute(
        select(Experiment).where(Experiment.experiment_id == experiment_id)
    ).scalar_one_or_none()


def list_experiments(
    session: Session,
    *,
    limit: int,
    offset: int,
    status: str | None = None,
) -> tuple[int, list[Experiment]]:
    stmt = select(Experiment)
    count_stmt = select(func.count()).select_from(Experiment)
    if status:
        stmt = stmt.where(Experiment.status == status)
        count_stmt = count_stmt.where(Experiment.status == status)
    total = int(session.execute(count_stmt).scalar_one())
    rows = (
        session.execute(stmt.order_by(Experiment.id.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return total, list(rows)


def request_cancellation(session: Session, experiment: Experiment) -> Experiment:
    """Cooperative cancellation: mark the flag; the worker honours it."""
    status = coerce(experiment.status)
    if is_terminal(status):
        raise ExperimentError(f"experiment already {status.value}")
    experiment.cancellation_requested = True
    if status == ExperimentStatus.QUEUED:
        assert_transition(status, ExperimentStatus.CANCELLED)
        experiment.status = ExperimentStatus.CANCELLED.value
        experiment.completed_at = utcnow()
    session.commit()
    session.refresh(experiment)
    return experiment


def transition(session: Session, experiment: Experiment, dst: ExperimentStatus) -> Experiment:
    assert_transition(coerce(experiment.status), dst)
    experiment.status = dst.value
    if dst == ExperimentStatus.RUNNING and experiment.started_at is None:
        experiment.started_at = utcnow()
    if is_terminal(dst):
        experiment.completed_at = utcnow()
    session.commit()
    session.refresh(experiment)
    return experiment


# --------------------------------------------------------------------- episodes
def load_episode_result(session: Session, episode_id: str) -> EpisodeResult | None:
    row = session.execute(
        select(Episode).where(Episode.episode_id == episode_id)
    ).scalar_one_or_none()
    if row is None:
        return None
    return _row_to_result(row)


def _row_to_result(row: Episode) -> EpisodeResult:
    return EpisodeResult(
        episode_id=row.episode_id,
        experiment_id=row.experiment_id,
        scenario_id=row.scenario_id,
        policy_name=row.policy_name,
        policy_version=row.policy_version,
        task_name=row.task_name,
        task_version=row.task_version,
        seed=row.seed,
        split=row.split,
        difficulty=row.difficulty,
        success=row.success,
        outcome=row.outcome,
        failure_category=row.failure_category,
        explanation=row.explanation,
        rule=row.rule,
        steps=row.steps,
        wall_clock_s=row.wall_clock_s,
        sim_time_s=row.sim_time_s,
        return_sum=row.return_sum,
        min_ee_target_dist_m=row.min_ee_target_dist_m,
        final_ee_target_dist_m=row.final_ee_target_dist_m,
        initial_ee_target_dist_m=row.initial_ee_target_dist_m,
        collision_steps=row.collision_steps,
        max_collision_count=row.max_collision_count,
        policy_inference_s=row.policy_inference_s,
        metrics=row.metrics or {},
        artifact_ref=row.artifact_ref,
        error=row.error,
    )


def list_episodes(
    session: Session,
    experiment_id: str,
    *,
    limit: int,
    offset: int,
    outcome: str | None = None,
    success: bool | None = None,
) -> tuple[int, list[Episode]]:
    stmt = select(Episode).where(Episode.experiment_id == experiment_id)
    count_stmt = (
        select(func.count()).select_from(Episode).where(Episode.experiment_id == experiment_id)
    )
    if outcome:
        stmt = stmt.where(Episode.outcome == outcome)
        count_stmt = count_stmt.where(Episode.outcome == outcome)
    if success is not None:
        stmt = stmt.where(Episode.success == success)
        count_stmt = count_stmt.where(Episode.success == success)
    total = int(session.execute(count_stmt).scalar_one())
    rows = session.execute(stmt.order_by(Episode.id).limit(limit).offset(offset)).scalars().all()
    return total, list(rows)


def experiment_metrics(session: Session, experiment_id: str) -> dict[str, Any]:
    rows = (
        session.execute(select(Episode).where(Episode.experiment_id == experiment_id))
        .scalars()
        .all()
    )
    results = [_row_to_result(r) for r in rows]
    timestep = _task_timestep(session, rows[0].task_name, rows[0].task_version) if rows else 0.005
    metrics = compute_metrics(results, timestep_s=timestep)
    return metrics.to_dict()


def _task_timestep(session: Session, task_name: str, task_version: str) -> float:
    task = session.execute(
        select(Task).where(Task.name == task_name, Task.version == task_version)
    ).scalar_one_or_none()
    if task and "timestep_s" in task.spec:
        return float(task.spec["timestep_s"])
    return 0.005


# ------------------------------------------------------------------ comparison
_COMPARABLE_FIELDS = (
    "task_name",
    "task_version",
    "suite_name",
    "suite_version",
    "suite_hash",
    "split",
)


def compare_experiments(
    session: Session,
    a_id: str,
    b_id: str,
    *,
    config: ComparisonConfig | None = None,
) -> dict[str, Any]:
    a = get_experiment(session, a_id)
    b = get_experiment(session, b_id)
    if a is None or b is None:
        raise ExperimentError("both experiments must exist")

    warnings: list[str] = []
    compatible = True
    for field in _COMPARABLE_FIELDS:
        va, vb = getattr(a, field), getattr(b, field)
        if va != vb:
            compatible = False
            warnings.append(f"incompatible evaluation setting: {field} differs ({va!r} vs {vb!r})")

    a_eps = {
        e.scenario_id: e
        for e in session.execute(select(Episode).where(Episode.experiment_id == a_id)).scalars()
    }
    b_eps = {
        e.scenario_id: e
        for e in session.execute(select(Episode).where(Episode.experiment_id == b_id)).scalars()
    }
    shared = sorted(set(a_eps) & set(b_eps))
    if len(shared) < 10:
        warnings.append(
            f"only {len(shared)} shared scenarios; sample size too small for strong conclusions"
        )

    ts_a = _ts(session, a)
    ts_b = _ts(session, b)
    pairs = [_build_pair(a_eps[sid], b_eps[sid], ts_a, ts_b) for sid in shared]

    comparison_config = config or ComparisonConfig()
    report = build_report(pairs, config=comparison_config)

    # Descriptive aggregate metrics over each arm (all episodes, not only shared).
    ma = compute_metrics([_row_to_result(e) for e in a_eps.values()], timestep_s=ts_a)
    mb = compute_metrics([_row_to_result(e) for e in b_eps.values()], timestep_s=ts_b)

    if not compatible:
        warnings.append(
            "evaluation settings differ; treat any change as confounded by configuration"
        )

    return {
        "a": a_id,
        "b": b_id,
        "compatible": compatible,
        "warnings": warnings + report.warnings,
        "n_scenarios_a": len(a_eps),
        "n_scenarios_b": len(b_eps),
        "shared_scenarios": len(shared),
        "metrics": [m.to_dict() for m in report.metrics],
        "failure_category_delta": _failure_delta(ma, mb),
        "sufficient_evidence": report.sufficient_evidence,
        "summary": report.summary,
        "aggregate_a": ma.to_dict(),
        "aggregate_b": mb.to_dict(),
    }


def _build_pair(a_row: Episode, b_row: Episode, ts_a: float, ts_b: float) -> PairedScenario:
    from simulation.runners.outcome import Outcome, is_infrastructure_failure

    def _infra(row: Episode) -> bool:
        try:
            return is_infrastructure_failure(Outcome(row.outcome))
        except ValueError:
            return False

    return PairedScenario(
        scenario_id=a_row.scenario_id,
        a_success=a_row.success,
        b_success=b_row.success,
        a_return=a_row.return_sum,
        b_return=b_row.return_sum,
        a_steps=float(a_row.steps),
        b_steps=float(b_row.steps),
        a_collision=float(a_row.collision_steps),
        b_collision=float(b_row.collision_steps),
        a_completion_s=a_row.steps * ts_a,
        b_completion_s=b_row.steps * ts_b,
        a_infrastructure_failure=_infra(a_row),
        b_infrastructure_failure=_infra(b_row),
    )


def _failure_delta(ma, mb) -> dict[str, int]:
    delta: dict[str, int] = {}
    for categories in (ma.failure_categories, mb.failure_categories):
        for key in categories:
            delta.setdefault(key, 0)
    for key in delta:
        delta[key] = mb.failure_categories.get(key, 0) - ma.failure_categories.get(key, 0)
    return delta


def _ts(session: Session, experiment: Experiment) -> float:
    return _task_timestep(session, experiment.task_name, experiment.task_version)


# ----------------------------------------------------------------- reproduction
def build_reproduction_spec(experiment: Experiment) -> ExperimentCreateSpec:
    """Rebuild the create spec from a persisted experiment (reproducibility)."""
    return ExperimentCreateSpec(
        name=f"{experiment.name} (reproduction)",
        description=f"Reproduction of {experiment.experiment_id}",
        policy_name=experiment.policy_name,
        policy_config=experiment.policy_config,
        task_name=experiment.task_name,
        task_version=experiment.task_version,
        suite_name=experiment.suite_name,
        suite_version=experiment.suite_version,
        split=experiment.split,
        dataset_version=experiment.dataset_version,
        seed=experiment.seeds.get("experiment_seed"),
        capture_every=experiment.eval_config.get("capture_every", 1),
        persist_artifacts=experiment.eval_config.get("persist_artifacts", True),
        timeout_s=experiment.eval_config.get("timeout_s"),
        code_revision=experiment.code_revision,
    )


def get_suite_data(
    session: Session, suite_name: str, suite_version: str
) -> ScenarioSuiteData | None:
    row = session.execute(
        select(ScenarioSuite).where(
            ScenarioSuite.suite_name == suite_name,
            ScenarioSuite.suite_version == suite_version,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return ScenarioSuiteData(
        suite_name=row.suite_name,
        suite_version=row.suite_version,
        task_name=row.task_name,
        task_version=row.task_version,
        scenarios=_scenarios_from_payload(row.payload),
        generator=row.generator,
    )


def _scenarios_from_payload(payload: dict[str, Any]):
    from simulation.scenarios.generator import Scenario

    return [
        Scenario(
            scenario_id=s["scenario_id"],
            task_name=s["task_name"],
            task_version=s["task_version"],
            seed=s["seed"],
            target_position=list(s["target_position"]),
            initial_qpos=s.get("initial_qpos"),
            qpos_noise=s.get("qpos_noise", 0.0),
            difficulty=s["difficulty"],
            split=s["split"],
            metadata=s.get("metadata", {}),
        )
        for s in payload.get("scenarios", [])
    ]


__all__ = [
    "ExperimentCreateSpec",
    "ExperimentError",
    "build_reproduction_spec",
    "compare_experiments",
    "create_experiment",
    "experiment_metrics",
    "get_experiment",
    "get_suite_data",
    "list_episodes",
    "list_experiments",
    "load_episode_result",
    "request_cancellation",
    "transition",
]
