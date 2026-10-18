.PHONY: help venv install dev-deps lint format typecheck test smoke clean

help:
	@echo "SimEval developer targets"
	@echo "  make venv        Create .venv with uv (Python 3.12)"
	@echo "  make install     Install runtime dependencies"
	@echo "  make dev-deps    Install test/lint/type-check tooling"
	@echo "  make lint        Run ruff check"
	@echo "  make format      Run ruff format"
	@echo "  make typecheck   Run mypy on core interfaces"
	@echo "  make test        Run pytest"
	@echo "  make smoke       Run the headless MuJoCo smoke test"
	@echo "  make clean       Remove caches"

PY := .venv/bin/python

venv:
	uv venv --python 3.12 .venv

install: venv
	uv pip install --python $(PY) \
		"mujoco>=3.2.3,<4.0" "numpy>=1.26,<3.0" \
		"fastapi>=0.115,<1.0" "uvicorn[standard]>=0.30,<1.0" \
		"pydantic>=2.9,<3.0" "pydantic-settings>=2.4,<3.0" \
		"sqlalchemy>=2.0.35,<3.0" "alembic>=1.13,<2.0" \
		"scipy>=1.14,<2.0" "pyyaml>=6.0,<7.0"

dev-deps: venv
	uv pip install --python $(PY) "pytest>=8.3,<9.0" "ruff>=0.6,<1.0" "mypy>=1.11,<2.0" "pytest-cov>=5.0,<7.0"

lint:
	$(PY) -m ruff check .

format:
	$(PY) -m ruff format .

typecheck:
	$(PY) -m mypy

test:
	$(PY) -m pytest

smoke:
	$(PY) scripts/smoke_sim.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
