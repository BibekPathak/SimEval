"""Experiment and episode routers."""

from __future__ import annotations

import math

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.db.session import get_session
from backend.app.models.entities import Experiment
from backend.app.schemas.experiment import (
    ArtifactSeriesOut,
    CompareOut,
    EpisodeArtifactsOut,
    EpisodeOut,
    ExperimentCreateIn,
    ExperimentDetailOut,
    ExperimentSummaryOut,
    ReproduceOut,
)
from backend.app.services import experiment_service as svc
from backend.app.services.state_machine import ExperimentStatus, is_terminal
from backend.app.workers.experiment_worker import get_worker

#: Array names TraceRecorder may write and a client may request. Shared with the
#: simulation layer so the two cannot silently diverge.
from simulation.runners.trace import RECORDED_ARRAY_NAMES

router = APIRouter()


def _summary(row: Experiment) -> ExperimentSummaryOut:
    return ExperimentSummaryOut(
        experiment_id=row.experiment_id,
        name=row.name,
        policy_name=row.policy_name,
        policy_version=row.policy_version,
        task_name=row.task_name,
        task_version=row.task_version,
        suite_name=row.suite_name,
        suite_version=row.suite_version,
        suite_hash=row.suite_hash,
        split=row.split,
        status=row.status,
        created_at=row.created_at.isoformat() if row.created_at else None,
        started_at=row.started_at.isoformat() if row.started_at else None,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        metrics=row.metrics or {},
    )


def _detail(row: Experiment) -> ExperimentDetailOut:
    base = _summary(row)
    return ExperimentDetailOut(
        **base.model_dump(),
        description=row.description,
        policy_config=row.policy_config or {},
        seeds=row.seeds or {},
        eval_config=row.eval_config or {},
        code_revision=row.code_revision,
        runtime_metadata=row.runtime_metadata or {},
        dataset_version=row.dataset_version,
        error=row.error,
        cancellation_requested=row.cancellation_requested,
    )


def _episode_out(row) -> EpisodeOut:
    return EpisodeOut(
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
        initial_ee_target_dist_m=row.initial_ee_target_dist_m,
        final_ee_target_dist_m=row.final_ee_target_dist_m,
        min_ee_target_dist_m=row.min_ee_target_dist_m,
        collision_steps=row.collision_steps,
        max_collision_count=row.max_collision_count,
        policy_inference_s=row.policy_inference_s,
        metrics=row.metrics or {},
        artifact_ref=row.artifact_ref,
        error=row.error,
    )


@router.post(
    "/experiments", response_model=ExperimentDetailOut, status_code=201, tags=["experiments"]
)
def create_experiment(
    payload: ExperimentCreateIn, session: Session = Depends(get_session)
) -> ExperimentDetailOut:
    spec = svc.ExperimentCreateSpec(
        name=payload.name,
        description=payload.description,
        policy_name=payload.policy_name,
        policy_config=payload.policy_config,
        task_name=payload.task_name,
        task_version=payload.task_version,
        suite_name=payload.suite_name,
        suite_version=payload.suite_version,
        split=payload.split,
        dataset_version=payload.dataset_version,
        seed=payload.seed,
        capture_every=payload.capture_every,
        persist_artifacts=payload.persist_artifacts,
        timeout_s=payload.timeout_s,
        code_revision=payload.code_revision,
    )
    try:
        row = svc.create_experiment(session, spec)
    except svc.ExperimentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _detail(row)


@router.get("/experiments", response_model=list[ExperimentSummaryOut], tags=["experiments"])
def list_experiments(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[ExperimentSummaryOut]:
    if status is not None:
        try:
            ExperimentStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"invalid status {status!r}") from exc
    _total, rows = svc.list_experiments(session, limit=limit, offset=offset, status=status)
    return [_summary(r) for r in rows]


@router.get("/experiments/compare", response_model=CompareOut, tags=["experiments"])
def compare_experiments(
    a: str = Query(...), b: str = Query(...), session: Session = Depends(get_session)
) -> CompareOut:
    try:
        payload = svc.compare_experiments(session, a, b)
    except svc.ExperimentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return CompareOut(**payload)


@router.get(
    "/experiments/{experiment_id}", response_model=ExperimentDetailOut, tags=["experiments"]
)
def get_experiment(
    experiment_id: str, session: Session = Depends(get_session)
) -> ExperimentDetailOut:
    row = svc.get_experiment(session, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return _detail(row)


@router.post(
    "/experiments/{experiment_id}/start",
    response_model=ExperimentDetailOut,
    tags=["experiments"],
)
def start_experiment(
    experiment_id: str, session: Session = Depends(get_session)
) -> ExperimentDetailOut:
    row = svc.get_experiment(session, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    status = ExperimentStatus(row.status)
    if is_terminal(status):
        raise HTTPException(status_code=409, detail=f"experiment already {status.value}")
    if status == ExperimentStatus.RUNNING:
        raise HTTPException(status_code=409, detail="experiment already running")
    get_worker().submit(experiment_id)
    return _detail(row)


@router.post(
    "/experiments/{experiment_id}/cancel",
    response_model=ExperimentDetailOut,
    tags=["experiments"],
)
def cancel_experiment(
    experiment_id: str, session: Session = Depends(get_session)
) -> ExperimentDetailOut:
    row = svc.get_experiment(session, experiment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    try:
        row = svc.request_cancellation(session, row)
    except svc.ExperimentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _detail(row)


@router.post(
    "/experiments/{experiment_id}/reproduce",
    response_model=ReproduceOut,
    status_code=201,
    tags=["experiments"],
)
def reproduce_experiment(
    experiment_id: str, session: Session = Depends(get_session)
) -> ReproduceOut:
    source = svc.get_experiment(session, experiment_id)
    if source is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    spec = svc.build_reproduction_spec(source)
    try:
        new_row = svc.create_experiment(session, spec)
    except svc.ExperimentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    get_worker().submit(new_row.experiment_id)
    return ReproduceOut(source_experiment_id=experiment_id, experiment=_detail(new_row))


@router.get(
    "/experiments/{experiment_id}/episodes",
    response_model=list[EpisodeOut],
    tags=["experiments"],
)
def get_experiment_episodes(
    experiment_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    outcome: str | None = Query(None),
    success: bool | None = Query(None),
    session: Session = Depends(get_session),
) -> list[EpisodeOut]:
    if svc.get_experiment(session, experiment_id) is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    _total, rows = svc.list_episodes(
        session, experiment_id, limit=limit, offset=offset, outcome=outcome, success=success
    )
    return [_episode_out(r) for r in rows]


@router.get("/experiments/{experiment_id}/metrics", tags=["experiments"])
def get_experiment_metrics(experiment_id: str, session: Session = Depends(get_session)) -> dict:
    if svc.get_experiment(session, experiment_id) is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return svc.experiment_metrics(session, experiment_id)


@router.get("/episodes/{episode_id}", response_model=EpisodeOut, tags=["episodes"])
def get_episode(episode_id: str, session: Session = Depends(get_session)) -> EpisodeOut:
    result = svc.load_episode_result(session, episode_id)
    if result is None:
        raise HTTPException(status_code=404, detail="episode not found")
    from backend.app.models.entities import Episode

    row = session.query(Episode).filter(Episode.episode_id == episode_id).one()
    return _episode_out(row)


@router.get(
    "/episodes/{episode_id}/artifacts",
    response_model=EpisodeArtifactsOut,
    tags=["episodes"],
)
def get_episode_artifacts(
    episode_id: str, session: Session = Depends(get_session)
) -> EpisodeArtifactsOut:
    from backend.app.models.entities import Episode

    row = session.query(Episode).filter(Episode.episode_id == episode_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="episode not found")
    from backend.app.core.config import get_settings
    from simulation.artifacts.store import LocalArtifactStore

    store = LocalArtifactStore(get_settings().artifact_root)
    exists = bool(row.artifact_ref) and store.exists(row.artifact_ref or "")
    arrays: dict[str, list[int]] = {}
    if exists and row.artifact_ref is not None:
        loaded = store.get_arrays(row.artifact_ref)
        arrays = {k: list(v.shape) for k, v in loaded.items()}
    return EpisodeArtifactsOut(
        episode_id=episode_id, artifact_ref=row.artifact_ref, exists=exists, arrays=arrays
    )


#: Names a client may request. Prevents arbitrary cache probing and keeps the
#: payload bounded. Mirrors the arrays written by TraceRecorder.
_ALLOWED_SERIES = RECORDED_ARRAY_NAMES


@router.get(
    "/episodes/{episode_id}/artifacts/series",
    response_model=ArtifactSeriesOut,
    tags=["episodes"],
)
def get_episode_artifact_series(
    episode_id: str,
    arrays: str = Query(
        default="",
        description=(
            "Comma-separated array names to return. Empty means the default set "
            f"({', '.join(sorted(_ALLOWED_SERIES))})."
        ),
    ),
    max_steps: int = Query(
        default=600, ge=1, le=5000, description="Cap on returned points per array"
    ),
    session: Session = Depends(get_session),
) -> ArtifactSeriesOut:
    from backend.app.core.config import get_settings
    from backend.app.models.entities import Episode
    from simulation.artifacts.store import LocalArtifactStore

    row = session.query(Episode).filter(Episode.episode_id == episode_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="episode not found")
    if not row.artifact_ref:
        raise HTTPException(status_code=404, detail="episode has no artifacts")

    store = LocalArtifactStore(get_settings().artifact_root)
    if not store.exists(row.artifact_ref):
        raise HTTPException(status_code=404, detail="artifact file is missing")

    requested = [a.strip() for a in arrays.split(",") if a.strip()] or sorted(
        {"source_step", "ee_target_dist", "qpos", "action", "collision", "reward"}
    )
    unknown = [a for a in requested if a not in _ALLOWED_SERIES]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown array(s) {unknown}; allowed: {sorted(_ALLOWED_SERIES)}",
        )

    loaded = store.get_arrays(row.artifact_ref)
    available = [a for a in requested if a in loaded]
    if not available:
        raise HTTPException(status_code=404, detail="requested arrays not present in artifact")

    n_steps = int(next(iter(loaded.values())).shape[0])
    stride = max(1, math.ceil(n_steps / max_steps))
    series: dict[str, list[float] | list[list[float]]] = {}
    returned = 0
    for name in available:
        arr = np.asarray(loaded[name], dtype=float)[::stride]
        returned = int(arr.shape[0])
        if arr.ndim == 1:
            series[name] = [float(x) for x in arr]
        elif arr.ndim == 2:
            series[name] = [[float(x) for x in row_values] for row_values in arr]
        # Higher-dimensional arrays are not exposed.

    return ArtifactSeriesOut(
        episode_id=episode_id,
        artifact_ref=row.artifact_ref,
        exists=True,
        n_steps=n_steps,
        stride=stride,
        returned_steps=returned,
        series=series,
    )
