"""Health and task/policy/suite routers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.session import get_session
from backend.app.models.entities import Policy, ScenarioSuite, Task
from backend.app.schemas.common import (
    HealthResponse,
    PolicyOut,
    SuiteCreateIn,
    SuiteDetailOut,
    SuiteSummaryOut,
    TaskOut,
)
from backend.app.services.suite_service import SuiteError, create_suite, get_suite, list_suites
from backend.app.workers.experiment_worker import get_worker
from simulation import __version__

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(session: Session = Depends(get_session)) -> HealthResponse:
    settings = get_settings()
    try:
        session.execute(select(Task.id).limit(1))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {type(exc).__name__}"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        app_name=settings.app_name,
        version=__version__,
        database=db_status,
        worker=get_worker().status(),
    )


@router.get("/tasks", response_model=list[TaskOut], tags=["tasks"])
def list_tasks(session: Session = Depends(get_session)) -> list[TaskOut]:
    rows = session.execute(select(Task).order_by(Task.name, Task.version)).scalars().all()
    return [
        TaskOut(name=r.name, version=r.version, description=r.description, spec=r.spec)
        for r in rows
    ]


@router.get("/policies", response_model=list[PolicyOut], tags=["policies"])
def list_policies(session: Session = Depends(get_session)) -> list[PolicyOut]:
    rows = session.execute(select(Policy).order_by(Policy.name, Policy.version)).scalars().all()
    return [
        PolicyOut(
            name=r.name,
            version=r.version,
            description=r.description,
            default_config=r.default_config,
        )
        for r in rows
    ]


def _suite_summary(row: ScenarioSuite) -> SuiteSummaryOut:
    return SuiteSummaryOut(
        suite_name=row.suite_name,
        suite_version=row.suite_version,
        task_name=row.task_name,
        task_version=row.task_version,
        content_hash=row.content_hash,
        n_scenarios=row.n_scenarios,
        counts=row.counts,
        created_at=row.created_at.isoformat() if row.created_at else None,
    )


@router.get("/scenario-suites", response_model=list[SuiteSummaryOut], tags=["scenario-suites"])
def get_scenario_suites(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[SuiteSummaryOut]:
    _total, rows = list_suites(session, limit=limit, offset=offset)
    return [_suite_summary(r) for r in rows]


@router.post(
    "/scenario-suites", response_model=SuiteDetailOut, status_code=201, tags=["scenario-suites"]
)
def post_scenario_suite(
    payload: SuiteCreateIn, session: Session = Depends(get_session)
) -> SuiteDetailOut:
    try:
        row = create_suite(
            session,
            suite_name=payload.suite_name,
            suite_version=payload.suite_version,
            task_name=payload.task_name,
            task_version=payload.task_version,
            n_scenarios=payload.n_scenarios,
            base_seed=payload.base_seed,
            dev_frac=payload.dev_frac,
            val_frac=payload.val_frac,
            qpos_noise=payload.qpos_noise,
        )
    except SuiteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _suite_detail(row)


@router.get(
    "/scenario-suites/{suite_name}/{suite_version}",
    response_model=SuiteDetailOut,
    tags=["scenario-suites"],
)
def get_scenario_suite(
    suite_name: str, suite_version: str, session: Session = Depends(get_session)
) -> SuiteDetailOut:
    row = get_suite(session, suite_name, suite_version)
    if row is None:
        raise HTTPException(status_code=404, detail="scenario suite not found")
    return _suite_detail(row)


def _suite_detail(row: ScenarioSuite) -> SuiteDetailOut:
    base = _suite_summary(row)
    return SuiteDetailOut(**base.model_dump(), generator=row.generator, payload=row.payload)
