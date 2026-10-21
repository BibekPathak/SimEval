# Single-container production image for SimEval.
#
# Stage 1 builds the React dashboard as static assets.
# Stage 2 runs the FastAPI backend (headless MuJoCo) and serves the built
# dashboard from the same origin, proxying /api to the backend.

# ---------------------------------------------------------------- frontend
FROM node:20-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------- backend
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SIMEVAL_DATABASE_URL=sqlite:////data/simeval.db \
    SIMEVAL_ARTIFACT_ROOT=/data/artifacts

WORKDIR /app

# git is used for optional code-revision metadata; no graphical stack is needed
# because evaluation is headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY simulation ./simulation
COPY scripts ./scripts
COPY configs ./configs

RUN pip install \
    "mujoco>=3.2.3,<4.0" "numpy>=1.26,<3.0" \
    "fastapi>=0.115,<1.0" "uvicorn[standard]>=0.30,<1.0" \
    "pydantic>=2.9,<3.0" "pydantic-settings>=2.4,<3.0" \
    "sqlalchemy>=2.0.35,<3.0" "alembic>=1.13,<2.0" \
    "scipy>=1.14,<2.0" "pyyaml>=6.0,<7.0" "httpx>=0.27"

# Built dashboard assets, served by the app's static mount.
COPY --from=frontend /web/dist ./frontend/dist

RUN mkdir -p /data/artifacts
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')" || exit 1

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
