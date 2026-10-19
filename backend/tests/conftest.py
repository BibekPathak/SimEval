"""Test configuration: isolated database and artifact root per test session."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_env() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="simeval-test-")
    os.environ["SIMEVAL_DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
    os.environ["SIMEVAL_ARTIFACT_ROOT"] = f"{tmp}/artifacts"
    # Reset caches so settings/db pick up the test values.
    from backend.app.core.config import get_settings
    from backend.app.db.session import reset_engine

    get_settings.cache_clear()
    reset_engine()
    yield
    get_settings.cache_clear()
    reset_engine()


@pytest.fixture()
def client() -> Iterator[TestClient]:  # noqa: F821
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def artifact_root() -> Path:
    from backend.app.core.config import get_settings

    return Path(get_settings().artifact_root)
