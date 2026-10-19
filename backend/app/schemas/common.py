"""Shared API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    version: str
    database: str
    worker: dict[str, Any]


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    status_code: int


class Page(BaseModel):
    total: int
    limit: int
    offset: int


class Paginated(BaseModel):
    page: Page
    items: list[Any] = Field(default_factory=list)


class TaskOut(BaseModel):
    name: str
    version: str
    description: str | None = None
    spec: dict[str, Any]


class PolicyOut(BaseModel):
    name: str
    version: str
    description: str | None = None
    default_config: dict[str, Any]


class SuiteSummaryOut(BaseModel):
    suite_name: str
    suite_version: str
    task_name: str
    task_version: str
    content_hash: str
    n_scenarios: int
    counts: dict[str, int]
    created_at: str | None = None


class SuiteDetailOut(SuiteSummaryOut):
    generator: dict[str, Any]
    payload: dict[str, Any]


class SuiteCreateIn(BaseModel):
    suite_name: str = Field(min_length=1, max_length=96)
    suite_version: str = Field(default="v1", min_length=1, max_length=32)
    task_name: str = "reach"
    task_version: str = "v1"
    n_scenarios: int = Field(default=30, ge=1, le=5000)
    base_seed: int = 1000
    dev_frac: float = Field(default=0.5, ge=0.0, le=1.0)
    val_frac: float = Field(default=0.25, ge=0.0, le=1.0)
    qpos_noise: float = Field(default=0.0, ge=0.0, le=1.0)
