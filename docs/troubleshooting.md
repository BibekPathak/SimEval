# Troubleshooting

Common issues and resolutions. SimEval is designed to run **headlessly**; most
problems are dependency or environment issues, not code issues.

## MuJoCo installation

**`ModuleNotFoundError: No module named 'mujoco'`**
Install the runtime dependencies: `make install` (or
`uv pip install --python .venv/bin/python "mujoco>=3.2.3,<4.0"`).

**`ImportError: ... libmujoco.so` / GLFW / EGL errors at import**
MuJoCo itself does not need a display. If you hit an error, it is usually from
attempting to *render*. Rendering is optional; evaluation never requires it.
Unset `MUJOCO_GL` to use the default and skip rendering.

## Rendering

Rendering is optional and only needed for frame/video capture. If
`scripts/smoke_sim.py --render` reports a skipped backend:

- **Desktop with a display/GPU:** try `MUJOCO_GL=glfw` (default on many Linux
  systems). This worked on the development machine.
- **Headless server without a GPU:** install OSMesa and set `MUJOCO_GL=osmesa`.
  On Debian/Ubuntu: `apt-get install libosmesa6`. The loader must be able to find
  `libOSMesa.so`.
- **GPU node:** `MUJOCO_GL=egl` requires a working EGL/DRM device. An EGL init
  failure does **not** affect metric computation.
- Install the optional extra for video: `uv pip install imageio imageio-ffmpeg`.

If none of these work, evaluation still functions fully without rendering.

## Database

**Tables missing / "no such table"**
Run migrations: `make migrate` (equivalent to `alembic upgrade head`). The app
also creates tables on startup, but Alembic is the authoritative path.

**Migration errors after changing models**
Generate a new migration: `make migration m="describe change"`, review the
generated file under `backend/alembic/versions/`, then `make migrate`.

## Worker / experiments stuck

**An experiment stays `RUNNING` after a crash**
On startup the worker requeues experiments left `RUNNING` (or marks them
`CANCELLED` if cancellation was requested). Restart the API to trigger recovery.
If it still appears stuck, check the process running the API has write access to
the database file.

**Experiments never start**
Confirm the worker is up via `GET /api/v1/health` (`worker.running` should be
`true`). Only a single bounded worker runs by default
(`SIMEVAL_MAX_CONCURRENT_EXPERIMENTS=1`); queued jobs run in order.

## Frontend

**Dashboard shows "API unreachable"**
Start the backend first (`make api`). In development the Vite server proxies
`/api` to `http://127.0.0.1:8000`; if your backend runs elsewhere, set
`VITE_API_BASE` and enable CORS origins via `SIMEVAL_CORS_ORIGINS`.

**`npm ci` fails / node version**
Use Node 20+ (`node --version`). CI uses Node 20.

**Port already in use**
Pass custom ports: `scripts/dev.sh 8001 5174`, or stop the conflicting process.

## Docker

**Build is slow**
The first build installs MuJoCo, NumPy, SciPy, and the frontend toolchain. Later
builds reuse cached layers.

**Healthcheck fails**
Give the container a few seconds; the first healthcheck can race startup. Check
logs with `docker compose logs simeval`.

**No GPU / rendering inside the container**
The image is headless by design. Rendering inside the container would require
adding OSMesa or a GPU runtime; it is not needed for evaluation.

## Disk space

Per-step artifacts are compressed `.npz` files. Reduce their size by increasing
`capture_every` in the experiment configuration, or set `persist_artifacts=false`.
The database stores only scalars and small JSON payloads.

## Getting more detail

- Structured logs go to stderr with `level=`, `logger=`, and `experiment=`
  fields.
- Reproduce the simulation layer alone: `make smoke`.
- Reproduce the full workflow: `make e2e`.
- Failures on a specific episode: inspect it in the dashboard or
  `GET /api/v1/episodes/{id}` — the `rule` and `explanation` fields state exactly
  why it was graded as it was.
