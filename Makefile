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
	@echo "  make e2e         Run the end-to-end API workflow smoke test"
	@echo "  make benchmark   Measure the pipeline and write docs/benchmarking.md"
	@echo "  make dev         Start backend + dashboard together"
	@echo "  make train-bc    Train the behavior-cloning policy (DAgger)"
	@echo "  make eval-bc     Evaluate the learned policy on held-out scenarios"
	@echo "  make compare-study  Multi-scenario policy comparison with CIs"
	@echo "  make api         Run the FastAPI backend (reload)"
	@echo "  make frontend-install  Install frontend dependencies"
	@echo "  make frontend-dev      Run the Vite dev server"
	@echo "  make frontend-build    Build the production frontend bundle"
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
	uv pip install --python $(PY) "pytest>=8.3,<9.0" "ruff>=0.6,<1.0" "mypy>=1.11,<2.0" "pytest-cov>=5.0,<7.0" "httpx>=0.27"

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

e2e:
	$(PY) scripts/smoke_e2e.py --n 8

benchmark:
	$(PY) scripts/benchmark.py --n 40 --write docs/benchmarking.md

dev:
	scripts/dev.sh

api:
	$(PY) -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload

migrate:
	$(PY) -m alembic upgrade head

migration:
	$(PY) -m alembic revision --autogenerate -m "$(m)"

demo2:
	$(PY) scripts/demo_m2.py --n 30

demo3:
	$(PY) scripts/demo_m3.py --n 24

demo4:
	$(PY) scripts/demo_m4.py --n 6

train-bc:
	$(PY) scripts/train_bc.py --mode dagger --iterations 6 --epochs 250

eval-bc:
	$(PY) scripts/eval_bc.py --n 120

compare-study:
	$(PY) scripts/compare_study.py --n 120

# --- frontend -----------------------------------------------------------------
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-check:
	cd frontend && npm run lint && npm run typecheck

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage _t.db _mig.db
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
