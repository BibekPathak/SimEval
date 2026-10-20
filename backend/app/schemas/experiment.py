"""Experiment and episode API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExperimentCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    policy_name: str
    policy_config: dict[str, Any] | None = None
    task_name: str = "reach"
    task_version: str = "v1"
    suite_name: str
    suite_version: str
    split: str = "all"
    dataset_version: str | None = None
    seed: int | None = None
    capture_every: int = Field(default=1, ge=1, le=1000)
    persist_artifacts: bool = True
    timeout_s: float | None = Field(default=None, ge=0.0)
    code_revision: str | None = None

    @field_validator("split")
    @classmethod
    def _valid_split(cls, v: str) -> str:
        allowed = {"all", "dev", "validation", "held_out"}
        if v not in allowed:
            raise ValueError(f"split must be one of {sorted(allowed)}")
        return v


class ExperimentSummaryOut(BaseModel):
    experiment_id: str
    name: str
    policy_name: str
    policy_version: str
    task_name: str
    task_version: str
    suite_name: str
    suite_version: str
    suite_hash: str
    split: str
    status: str
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    metrics: dict[str, Any]


class ExperimentDetailOut(ExperimentSummaryOut):
    description: str | None = None
    policy_config: dict[str, Any]
    seeds: dict[str, Any]
    eval_config: dict[str, Any]
    code_revision: str | None = None
    runtime_metadata: dict[str, Any]
    dataset_version: str | None = None
    error: str | None = None
    cancellation_requested: bool


class EpisodeOut(BaseModel):
    episode_id: str
    experiment_id: str
    scenario_id: str
    policy_name: str
    policy_version: str
    task_name: str
    task_version: str
    seed: int
    split: str
    difficulty: str
    success: bool
    outcome: str
    failure_category: str | None
    explanation: str
    rule: str
    steps: int
    wall_clock_s: float
    sim_time_s: float
    return_sum: float
    initial_ee_target_dist_m: float
    final_ee_target_dist_m: float
    min_ee_target_dist_m: float
    collision_steps: int
    max_collision_count: int
    policy_inference_s: float
    metrics: dict[str, Any]
    artifact_ref: str | None
    error: str | None


class EpisodeArtifactsOut(BaseModel):
    episode_id: str
    artifact_ref: str | None
    exists: bool
    arrays: dict[str, list[int]]


class ComparisonMetric(BaseModel):
    metric: str
    unit: str = ""
    direction: str = "neutral"
    a: float | None
    b: float | None
    delta: float | None
    relative: float | None
    ci_low: float | None = None
    ci_high: float | None = None
    confidence: float = 0.95
    method: str = ""
    n_pairs: int = 0
    verdict: str = "MISSING"
    reason: str = ""


class CompareOut(BaseModel):
    a: str
    b: str
    compatible: bool
    warnings: list[str]
    n_scenarios_a: int
    n_scenarios_b: int
    shared_scenarios: int
    metrics: list[ComparisonMetric]
    failure_category_delta: dict[str, int]
    sufficient_evidence: bool = False
    summary: str = ""


class ReproduceOut(BaseModel):
    source_experiment_id: str
    experiment: ExperimentDetailOut
