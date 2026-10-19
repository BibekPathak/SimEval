"""ORM models for SimEval.

Logical shapes follow ``docs/data-model.md``. Large per-step arrays are never
stored here; only artifact references are.

Entities:
  Task           -- a versioned task definition available for evaluation.
  Policy         -- a registered policy (name + version + default config).
  ScenarioSuite  -- a versioned, hashed collection of scenarios (JSON payload).
  Experiment     -- a run binding policy + suite + task + config + seeds.
  Episode        -- one graded episode result belonging to an experiment.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.session import Base, utcnow


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_task_name_version"),)


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_policy_name_version"),)


class ScenarioSuite(Base):
    __tablename__ = "scenario_suites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    suite_name: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    suite_version: Mapped[str] = mapped_column(String(32), nullable=False)
    task_name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    n_scenarios: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    generator: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("suite_name", "suite_version", name="uq_suite_name_version"),
    )


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Bindings.
    policy_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    task_name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_version: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_name: Mapped[str] = mapped_column(String(96), nullable=False)
    suite_version: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    split: Mapped[str] = mapped_column(String(16), nullable=False, default="all")
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Evaluation configuration + provenance.
    seeds: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    eval_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    code_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runtime_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Lifecycle.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="QUEUED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Aggregated metrics (JSON), populated on completion.
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    episodes: Mapped[list[Episode]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
        order_by="Episode.id",
    )


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    experiment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("experiments.experiment_id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    policy_name: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    task_name: Mapped[str] = mapped_column(String(64), nullable=False)
    task_version: Mapped[str] = mapped_column(String(32), nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    split: Mapped[str] = mapped_column(String(16), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)

    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    failure_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rule: Mapped[str] = mapped_column(Text, nullable=False, default="")

    steps: Mapped[int] = mapped_column(Integer, nullable=False)
    wall_clock_s: Mapped[float] = mapped_column(Float, nullable=False)
    sim_time_s: Mapped[float] = mapped_column(Float, nullable=False)
    return_sum: Mapped[float] = mapped_column(Float, nullable=False)
    initial_ee_target_dist_m: Mapped[float] = mapped_column(Float, nullable=False)
    final_ee_target_dist_m: Mapped[float] = mapped_column(Float, nullable=False)
    min_ee_target_dist_m: Mapped[float] = mapped_column(Float, nullable=False)
    collision_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    max_collision_count: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_inference_s: Mapped[float] = mapped_column(Float, nullable=False)

    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    artifact_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    experiment: Mapped[Experiment] = relationship(back_populates="episodes")

    __table_args__ = (
        Index("ix_episodes_experiment_outcome", "experiment_id", "outcome"),
        Index("ix_episodes_experiment_scenario", "experiment_id", "scenario_id"),
    )


__all__ = ["Episode", "Experiment", "Policy", "ScenarioSuite", "Task"]
