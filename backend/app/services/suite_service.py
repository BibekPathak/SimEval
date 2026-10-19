"""Scenario suite service: create from the generator and persist."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.db.session import utcnow
from backend.app.models.entities import ScenarioSuite
from simulation.scenarios.generator import generate_suite


class SuiteError(RuntimeError):
    pass


def create_suite(
    session: Session,
    *,
    suite_name: str,
    suite_version: str,
    task_name: str,
    task_version: str,
    n_scenarios: int,
    base_seed: int,
    dev_frac: float,
    val_frac: float,
    qpos_noise: float,
) -> ScenarioSuite:
    existing = session.execute(
        select(ScenarioSuite).where(
            ScenarioSuite.suite_name == suite_name,
            ScenarioSuite.suite_version == suite_version,
        )
    ).scalar_one_or_none()

    data = generate_suite(
        suite_name=suite_name,
        suite_version=suite_version,
        task_name=task_name,
        task_version=task_version,
        n_scenarios=n_scenarios,
        base_seed=base_seed,
        dev_frac=dev_frac,
        val_frac=val_frac,
        qpos_noise=qpos_noise,
    )

    if existing is not None:
        if existing.content_hash == data.content_hash():
            return existing
        raise SuiteError(
            f"suite {suite_name} {suite_version} already exists with a different "
            f"content hash ({existing.content_hash[:8]} != {data.content_hash()[:8]}); "
            "choose a new suite_version"
        )

    row = ScenarioSuite(
        suite_name=data.suite_name,
        suite_version=data.suite_version,
        task_name=data.task_name,
        task_version=data.task_version,
        content_hash=data.content_hash(),
        n_scenarios=len(data.scenarios),
        counts=data.counts(),
        generator=data.generator,
        payload=data.to_dict(),
        created_at=utcnow(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_suites(session: Session, *, limit: int, offset: int) -> tuple[int, list[ScenarioSuite]]:
    total = int(session.execute(select(func.count()).select_from(ScenarioSuite)).scalar_one())
    rows = (
        session.execute(
            select(ScenarioSuite).order_by(ScenarioSuite.id.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return total, list(rows)


def get_suite(session: Session, suite_name: str, suite_version: str) -> ScenarioSuite | None:
    return session.execute(
        select(ScenarioSuite).where(
            ScenarioSuite.suite_name == suite_name,
            ScenarioSuite.suite_version == suite_version,
        )
    ).scalar_one_or_none()


__all__ = ["SuiteError", "create_suite", "get_suite", "list_suites"]
