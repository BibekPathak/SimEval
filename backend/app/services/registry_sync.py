"""Sync simulation-layer registries into the database.

The simulation package is the source of truth for available tasks and policies.
This service makes them queryable via the API by upserting them into the DB on
startup (idempotent).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import utcnow
from backend.app.models.entities import Policy, Task
from simulation.environments.reach_task import DEFAULT_REACH_SPEC
from simulation.policies.registry import available_policies


def sync_registries(session: Session) -> None:
    _sync_tasks(session)
    _sync_policies(session)
    session.commit()


def _sync_tasks(session: Session) -> None:
    spec = DEFAULT_REACH_SPEC
    existing = session.execute(
        select(Task).where(Task.name == spec.task_name, Task.version == spec.task_version)
    ).scalar_one_or_none()
    payload = {
        "success_distance_m": spec.success_distance_m,
        "success_dwell_steps": spec.success_dwell_steps,
        "max_steps": spec.max_steps,
        "timestep_s": spec.timestep_s,
        "collision_is_floor_contact": spec.collision_is_floor_contact,
    }
    if existing is None:
        session.add(
            Task(
                name=spec.task_name,
                version=spec.task_version,
                description="Planar 4-DOF reach task (self-authored MJCF).",
                spec=payload,
                created_at=utcnow(),
            )
        )
    else:
        existing.spec = payload


def _sync_policies(session: Session) -> None:
    for entry in available_policies():
        existing = session.execute(
            select(Policy).where(Policy.name == entry["name"], Policy.version == entry["version"])
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Policy(
                    name=entry["name"],
                    version=entry["version"],
                    description=entry["description"],
                    default_config=entry["default_config"],
                    created_at=utcnow(),
                )
            )
        else:
            existing.description = entry["description"]
            existing.default_config = entry["default_config"]


__all__ = ["sync_registries"]
