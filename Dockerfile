# SimEval backend image. Headless MuJoCo; no display required.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SIMEVAL_DATABASE_URL=sqlite:////data/simeval.db \
    SIMEVAL_ARTIFACT_ROOT=/data/artifacts

WORKDIR /app

# System deps: git for code revision metadata; libgl for optional rendering.
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

RUN mkdir -p /data/artifacts
VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
