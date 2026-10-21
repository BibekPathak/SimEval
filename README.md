# SimEval — Simulation-Driven Robot Learning Evaluation Platform

> **Status: Milestone 2 complete.** The repository contains the project
> scaffold, tooling, CI, a verified headless MuJoCo smoke test, a real 4-DOF
> **reach environment**, a **policy interface** with two functioning
> controllers, and **versioned, seeded scenario generation** with
> dev/validation/held-out splits. The evaluation engine, experiment management,
> statistics, API, and dashboard arrive in later milestones
> (see [Roadmap](#roadmap)).

SimEval is an evaluation-first platform for measuring the performance,
robustness, and generalization of robot-learning policies in simulation. The
central question it answers is:

> **Did this policy actually improve, under which conditions, and what evidence
> supports that conclusion?**

This is a research/portfolio-grade system, not a production deployment. Every
metric is intended to be traceable to real recorded episode data. Simulator
results, unit-test fixtures, and synthetic data are kept explicitly separate,
and no benchmark numbers or improvements are ever fabricated.

## What works today

### Milestone 1 — scaffold, tooling, simulator probe

- Repository layout separating simulation, backend, and frontend concerns.
- Pinned Python tooling (`ruff`, `mypy`, `pytest`) with a `Makefile`.
- A **real** MuJoCo capability probe, `scripts/smoke_sim.py`, that:
  - parses a self-authored MJCF reach model,
  - resets with an explicit seed and steps real physics,
  - verifies bit-for-bit determinism across repeated rollouts,
  - reads ground-truth end-effector/target geometry and contact counts,
  - optionally renders an offscreen frame when a GL backend is available.
- GitHub Actions CI running lint, format check, type check, tests, and the
  headless smoke test.

### Milestone 2 — environment, policies, scenarios

- `simulation/environments/reach_env.py`: a seeded 4-DOF reach task built on a
  self-authored MJCF model (`reach_mjcf.py`), with:
  - explicit-seed reset (plus optional initial posture / joint noise),
  - Gymnasium-style observations, action validation, and NaN/Inf handling,
  - termination on sustained success (dwell window) and truncation at a fixed
    step budget,
  - ground-truth end-effector/target geometry and an exact EE-vs-floor contact
    count.
- `simulation/policies/`: a `Policy` interface plus two genuinely different,
  deterministic controllers:
  - **baseline** `ik_planner_baseline` — full inverse-kinematics setpoint
    planner (global solve each step),
  - **candidate** `resolved_rate_candidate` — incremental resolved-rate
    controller (local Jacobian feedback from the live state).
- `simulation/scenarios/generator.py`: versioned, seeded scenario suites with
  `easy`/`medium`/`hard` tiers, adversarial initial postures, deterministic
  split assignment, a leakage guard, and save/load round-tripping.
- `configs/scenario_suite_reach_default_v1.json`: a committed example suite.
- Unit tests covering reset determinism, termination/truncation, invalid-action
  handling, success dwell, policy behaviour and determinism, and split
  isolation.

### Milestone 3 — runner, metrics, grader, artifacts

- `simulation/runners/episode_runner.py`: executes one scenario for one policy
  end to end — builds the env, resets with the scenario seed, steps the policy
  under step/timeout/safety limits, records a trace, persists it, and returns a
  graded `EpisodeResult`. Environment/construction/simulator errors are
  captured, never raised past the runner, and never counted as success.
- `simulation/runners/trace.py`: `TraceRecorder` captures per-step state
  (qpos, qvel, EE/target pose, distance, action, reward, contacts) at a
  configurable frequency, always keeping the initial step.
- `simulation/graders/reach_grader.py`: deterministic, task-specific grader that
  maps recorded evidence to a structured outcome with the deciding rule and an
  explanation. **Task failures** (`TIMEOUT`, `TARGET_NOT_REACHED`, `COLLISION`)
  are separated from **infrastructure failures** (`SIMULATOR_ERROR`,
  `INVALID_ACTION`, `NUMERICAL_FAILURE`). The grader is testable without a
  simulator.
- `simulation/metrics/reach_metrics.py`: aggregate metrics computed from
  persisted episodes — success rate (with numerator/denominator), completion
  time (successes only), episode length, collision rate/steps, return
  mean/median, throughput, and inference latency. Infrastructure failures are
  excluded from denominators by default and reported separately.
- `simulation/artifacts/store.py`: `ArtifactStore` abstraction with a
  filesystem-backed `LocalArtifactStore` writing compressed `.npz` arrays under
  a fixed root, with traversal/absolute-path rejection and a schema version.
- 42 new tests covering grader rules, metric math, artifact round-trips and
  path safety, runner termination/error handling, and reproducibility.

### Milestone 4 — experiment API, worker, persistence, reproducibility

- `backend/app/`: FastAPI application with structured logging, settings, and
  consistent error responses.
- SQLAlchemy 2.x models (`Task`, `Policy`, `ScenarioSuite`, `Experiment`,
  `Episode`) with unique constraints and indexes; **Alembic** migrations
  (`backend/alembic/`) that upgrade and downgrade cleanly.
- `backend/app/services/experiment_service.py`: experiment creation with binding
  validation, an enforced **state machine** (`QUEUED → RUNNING → COMPLETED`,
  plus `FAILED`/`CANCELLED`), cooperative cancellation, metric aggregation,
  compatibility-aware comparison, and reproduction-from-config.
- `backend/app/workers/experiment_worker.py`: a **bounded local worker** (single
  thread, configurable concurrency) that executes real episodes, persists them,
  and **recovers interrupted experiments** on restart (no job is left "running
  forever"). Cancellation is checked between episodes.
- REST API under `/api/v1` (see below), with Pydantic validation and OpenAPI
  docs at `/docs`. No API parameter is ever a filesystem path; no user code is
  executed.
- `scripts/demo_m4.py`: full API lifecycle demo.
- Dockerfile and docker-compose for a one-command container run.

#### API endpoints (Milestone 4)

```text
GET  /api/v1/health
GET  /api/v1/tasks
GET  /api/v1/policies
GET  /api/v1/scenario-suites
POST /api/v1/scenario-suites
GET  /api/v1/scenario-suites/{suite_name}/{suite_version}
POST /api/v1/experiments
GET  /api/v1/experiments
GET  /api/v1/experiments/compare?a=&b=
GET  /api/v1/experiments/{id}
POST /api/v1/experiments/{id}/start
POST /api/v1/experiments/{id}/cancel
POST /api/v1/experiments/{id}/reproduce
GET  /api/v1/experiments/{id}/episodes
GET  /api/v1/experiments/{id}/metrics
GET  /api/v1/episodes/{id}
GET  /api/v1/episodes/{id}/artifacts
```

### Milestone 6 — React dashboard

- `frontend/`: Vite + React 18 + TypeScript + Tailwind CSS single-page app. It
  consumes only the `/api/v1` REST endpoints (no mocked data, no backend
  imports). A Vite dev proxy forwards `/api` to the backend so no CORS setup is
  required in development; CORS is also enabled on the backend for direct access.
- Pages:
  - **Overview** — experiment/suite/task counts, latest evaluation, success-rate
    trend, and a simple same-policy regression watch, plus a path to create an
    evaluation.
  - **Tasks & Suites** — tasks with their specs, scenario suites with split
    counts, and a scenario inspector.
  - **New Evaluation** — task/policy/suite/split selection, limits, validation,
    a review panel, and create-and-start.
  - **Experiment details** — status, aggregate metrics, outcome distribution,
    configuration, and a filterable, sortable episode table.
  - **Policy comparison** — per-metric deltas with **95% intervals, verdicts,
    per-arm Wilson intervals, an evidence verdict, and compatibility warnings**
    (the M5 statistics surfaced in the UI).
  - **Episode inspection** — outcome, the grader's deciding rule and explanation,
    recorded scalars, and the persisted artifact array shapes.
- Honest data handling: the episode inspector shows recorded evidence and
  artifact **shapes**; it does not display reconstructed or invented
  trajectories. Per-step array plotting awaits an array-content endpoint.
- `npm run lint`, `npm run typecheck`, and `npm run build` all pass; CI runs them.

### Milestone 7 — packaging, docs, and end-to-end verification

- **Single-container production image:** a multi-stage `Dockerfile` builds the
  React dashboard and serves it from the same origin as the API (SPA fallback),
  so `docker compose up --build` gives one URL for both.
- **One-command development:** `scripts/dev.sh` (or `make dev`) applies
  migrations and starts the backend and dashboard together.
- **End-to-end smoke test:** `scripts/smoke_e2e.py` (`make e2e`) drives the whole
  workflow through the real API, database, worker, and simulator on an isolated
  temp database, including restart persistence.
- **Benchmark harness:** `scripts/benchmark.py` (`make benchmark`) measures real
  throughput/latency and regenerates `docs/benchmarking.md`.
- **Documentation:** `docs/architecture.md`, `evaluation-methodology.md`,
  `data-model.md`, `benchmarking.md`, `limitations.md`, `research-log.md`, and
  `troubleshooting.md`.
- **CI** runs backend lint/format/type-check/tests, a migration up/down check,
  the headless smoke test, and the frontend lint/type-check/build.

### Verified smoke-test output

```
====================================================================
SimEval simulator smoke test (Milestone 1)
====================================================================
python         : 3.12.7
platform       : Linux ... (x86_64)
mujoco         : 3.16.0
mjcf sha256/16 : 798b0b74735b45f0
model          : nq=3 nu=3 nbody=7 ngeom=7
rollout        : 400 steps, seed=1234
--------------------------------------------------------------------
[PASS] import_mujoco    mujoco 3.16.0
[PASS] parse_mjcf       nq=3 nu=3 nbody=7
[PASS] determinism      max|qpos_a - qpos_b| = 0.000e+00 over 400 steps
[PASS] finite_state     all qpos finite: True
[PASS] task_geometry    initial=0.1769 m -> final=0.0000 m (min=0.0000 m, success<0.05 m: True)
[PASS] contacts         ncon at end of rollout = 0
--------------------------------------------------------------------
SMOKE TEST: OK
====================================================================
```

Reproducibility was confirmed across independent process invocations
(identical results to 10 decimal places).

### Milestone 2 demo — both policies on one seeded suite

`scripts/demo_m2.py` runs real rollouts of both policies against the **same**
versioned scenarios and prints per-difficulty success counts. This is a manual
integration check, not the full metric pipeline (that is Milestone 3).

```console
$ .venv/bin/python scripts/demo_m2.py --n 30
====================================================================
SimEval Milestone 2 demo — real rollouts, no mocks
====================================================================
suite reach-default v1  hash=81dccc488dfc530a  counts={'dev': 15, 'validation': 8, 'held_out': 7}
split: all
--------------------------------------------------------------------
baseline   ik_planner_baseline      success 26/30 (86.7%)
    easy    10/10
    hard    8/10
    medium  8/10
candidate  resolved_rate_candidate  success 25/30 (83.3%)
    easy    10/10
    hard    7/10
    medium  8/10
====================================================================
```

These are actual results from the committed code and example suite on the
development machine; they are not benchmark claims. Re-running with the same
suite hash reproduces them exactly.

### Milestone 3 demo — run, grade, aggregate

`scripts/demo_m3.py` runs the full evaluation pipeline (runner → trace →
artifact → grader → metrics) for one policy over a suite and prints the
aggregate metric set.

```console
$ .venv/bin/python scripts/demo_m3.py --n 24
======================================================================
SimEval Milestone 3 demo — run -> grade -> aggregate (real episodes)
======================================================================
suite reach-default v1 hash=8914bc14392724a8
policy: ik_planner_baseline   split: all   capture_every: 1
----------------------------------------------------------------------
episodes total          : 24
evaluated (in denominator): 24
infrastructure failures : 0
success                 : 20/24  (83.3%)
failure rate            : 16.7%
completion time mean    : 0.2078 s (successes only)
episode length mean     : 101.2917 steps
collision rate          : 0.0%
return mean / median    : 0.8333 / 1.0000
throughput              : 8.4531 episodes/s
mean policy inference   : 102.1819 ms/episode
failure categories      : {'TIMEOUT': 4}
artifact round-trip ok  : True
======================================================================
```

These values come from real MuJoCo rollouts on the development machine.
Throughput and latency are indicative only (no GPU; single CPU process).

### Milestone 4 demo — API lifecycle

`scripts/demo_m4.py` drives the full API: create a suite, run two policies
through the worker, compare them, inspect an episode's artifacts, and reproduce
an experiment. (Uses an in-process TestClient against the real DB, worker, and
simulator.)

```console
$ .venv/bin/python scripts/demo_m4.py --n 6
======================================================================
SimEval Milestone 4 demo — experiment API lifecycle (real worker + sim)
======================================================================
suite demo-m4 hash=254420ba3ac9ccd6
----------------------------------------------------------------------
ik_planner_baseline      status=COMPLETED episodes=6 success=5/6
resolved_rate_candidate  status=COMPLETED episodes=6 success=5/6
----------------------------------------------------------------------
comparison compatible=True shared=6
  success_rate                 a=0.8333 b=0.8333 delta=0.0000
  episode_length_mean_steps    a=99.1667 b=234.1667 delta=135.0000
  completion_time_mean_s       a=0.1950 b=1.0050 delta=0.8100
  collision_rate               a=0.0000 b=0.0000 delta=0.0000
  return_mean                  a=0.8333 b=0.8333 delta=0.0000
  ! only 6 shared scenarios; sample size too small for strong conclusions
----------------------------------------------------------------------
episode exp_...-demo-m4-v1-0000-... outcome=SUCCESS final_dist=0.0306 m
artifacts exists=True arrays=['action', 'collision', 'ee_pos', ...]
reproduction exp_... from exp_... hash_match=True
======================================================================
```

This is a point-estimate comparison only: **no confidence intervals** are
computed yet (Milestone 5).

### Milestone 5 statistics — surfaced in the dashboard

The M5 comparison engine (Wilson intervals, paired bootstrap, verdicts,
regression thresholds) is exposed through `GET /api/v1/experiments/compare` and
rendered on the **Compare** page. See `docs/evaluation-methodology.md` for the
definitions and `docs/research-log.md` for the reasoning behind the thresholds.

### Milestone 6 dashboard — verified workflow

The dashboard was exercised against a live backend (real worker + simulator)
using an in-browser run. Verified end to end:

1. **Overview** rendered live counts (2 experiments, 1 suite, 1 task), the latest
   evaluation (10/12, 83.3%), and the success-rate trend — all from the API.
2. **Compare** for the two runs rendered the M5 statistics: `episode_length_mean_steps`
   and `completion_time_mean_s` marked **REGRESSED** with 95% intervals, success
   rate **INCONCLUSIVE**, and per-arm Wilson intervals.
3. **Experiment details** listed aggregate metrics, the outcome distribution, and
   a sortable episode table.
4. **Episode inspection** showed the grader's deciding rule, the explanation, the
   recorded scalars, and the artifact array shapes (e.g. `qpos [81, 4]`).
5. **New evaluation** validated input, created and started an experiment, and the
   details page polled it through `RUNNING → COMPLETED`.

No screenshot is embedded here; the workflow above is reproducible with
`make api` + `make frontend-dev` and the steps in *Running the dashboard*.

### Requirement: the complete workflow (Milestone 7)

The full workflow from §17 of the project brief was executed and verified. The
commands and their actual output:

**1–2. Start the application and open the dashboard.**

```console
$ make migrate && make api        # backend on :8000, dashboard bundled in container
$ docker compose up --build       # OR: single container serving UI + API on :8000
```

**3–4. Select a suite and run the baseline policy.**

```console
$ curl -s -X POST localhost:8000/api/v1/scenario-suites \
    -H 'content-type: application/json' \
    -d '{"suite_name":"demo","suite_version":"v1","n_scenarios":12}'
{"suite_name":"demo","content_hash":"73cf3cb5bf59c0f6","counts":{"dev":5,"validation":4,"held_out":3}}
```

**5–8. Run both policies, inspect outcomes, compare, and inspect a failure.**
Reproduced deterministically by the end-to-end smoke test:

```console
$ make e2e
==================================================================
SimEval end-to-end smoke test
==================================================================
[PASS] health               ok
[PASS] create_suite         d6c3ba332f6ff18b
[PASS] run_ik_planner_baseline 7/8 success
[PASS] run_resolved_rate_candidate 7/8 success
[PASS] compare              Inconclusive: only 8 paired scenarios. Report point estimates as descriptive only; no improvement/regression claim is supported.
[PASS] inspect_failure      TIMEOUT: steps >= max_steps (400) without success
[PASS] reproduce            exp_7253a3fb01124c97 matches original
[PASS] restart_persistence  COMPLETED
==================================================================
E2E: OK
==================================================================
```

**9. Re-run an experiment from its saved configuration** — the `reproduce` step
above rebuilds the experiment from stored policy config, suite version, and
seeds, and confirms an identical success count.

**10. Restart and confirm results persist** — the `restart_persistence` step
re-enters the application lifespan and re-reads the completed experiment.

**Containerized verification (real Docker image):**

```console
$ docker build -t simeval:test . && docker run -d -p 8899:8000 simeval:test
$ curl -s localhost:8899/api/v1/health           # status: ok
$ curl -s localhost:8899/ | grep title           # <title>SimEval — Robot Learning Evaluation</title>
# running a 10-scenario experiment inside the container:
#   status COMPLETED · metrics {n_success: 9, n_evaluated: 10, success_rate: 0.9}
#   episode0 SUCCESS · artifact persisted
```

All steps above were executed on the development machine. No unexecuted
workflow is reported as verified.

## Requirements

- Python 3.11–3.12 (3.12 verified)
- [uv](https://docs.astral.sh/uv/) for environment and dependency management
- MuJoCo runs **headlessly by default**; no graphical desktop is required for
  the smoke test or (later) metric computation.
- Rendering frames is **optional** and needs a working MuJoCo GL backend
  (`glfw`, `egl`, or `osmesa`). Without one, rendering is reported as skipped,
  not failed.

## Quick start

```bash
# 1. Create the virtual environment and install dependencies
make venv
make install
make dev-deps

# 2. Run the real, headless simulation smoke test
make smoke
# or: .venv/bin/python scripts/smoke_sim.py
#     .venv/bin/python scripts/smoke_sim.py --render   # also capture a frame

# 3. Run the Milestone 2 demo (both policies on one seeded suite)
.venv/bin/python scripts/demo_m2.py --n 30

# 4. Run the Milestone 3 demo (full pipeline: run -> grade -> aggregate)
.venv/bin/python scripts/demo_m3.py --n 24
.venv/bin/python scripts/demo_m3.py --n 24 --policy resolved_rate_candidate --split held_out

# 5. Run the Milestone 4 demo (API lifecycle: run -> compare -> reproduce)
.venv/bin/python scripts/demo_m4.py --n 6

# 6. Verify the complete workflow end to end (isolated temp DB)
make e2e

# 7. Measure the pipeline (writes docs/benchmarking.md)
make benchmark

# 8. Run the quality gates
make lint
make typecheck
make test
```

### Running the dashboard

```bash
# Terminal 1: backend API (must be running for the dashboard)
make migrate
make api                 # http://127.0.0.1:8000

# Terminal 2: frontend dev server (proxies /api to the backend)
make frontend-install    # first time only
make frontend-dev        # http://127.0.0.1:5173

# Production bundle
make frontend-build      # emits frontend/dist
```

The dashboard reads exclusively from the REST API. Create a scenario suite and
a couple of experiments (via the UI or `curl`) to populate the views.

### One-command development

```bash
scripts/dev.sh          # or: make dev
# starts the backend on :8000 and the dashboard on :5173, applying migrations
```

### Running the API

```bash
# Apply migrations and start the server
make migrate
make api           # http://127.0.0.1:8000  (OpenAPI docs at /docs)

# Or with the helper script
scripts/run_api.sh 127.0.0.1 8000

# Example requests
curl -s localhost:8000/api/v1/health
curl -s -X POST localhost:8000/api/v1/scenario-suites \
  -H 'content-type: application/json' \
  -d '{"suite_name":"demo","suite_version":"v1","n_scenarios":8}'
curl -s -X POST localhost:8000/api/v1/experiments \
  -H 'content-type: application/json' \
  -d '{"name":"baseline","policy_name":"ik_planner_baseline","suite_name":"demo","suite_version":"v1"}'

# Docker
docker compose up --build
```

### Rendering troubleshooting

If `--render` reports a skipped backend:

- On a machine with a display/GPU, MuJoCo may work with `MUJOCO_GL=glfw`
  (default on many Linux setups).
- On headless servers, install OSMesa and set `MUJOCO_GL=osmesa`, e.g.
  `apt-get install libosmesa6` (Debian/Ubuntu). Some distributions name the
  package differently; `libOSMesa.so` must be discoverable by the loader.
- EGL requires a working EGL/DRM device; `MUJOCO_GL=egl` is common on GPU
  nodes. A failed EGL init does not affect metric computation.
- The optional `render` extra (`imageio`, `imageio-ffmpeg`) is only needed for
  frame/video capture, not for evaluation.

## Repository layout

```
simeval/
  backend/
    app/                FastAPI app: api, core, db, models, schemas, services, workers
    alembic/            Database migrations
    tests/              Backend tests (API, state machine, worker)
  simulation/
    environments/       MJCF models, reach task, env, kinematics
    policies/           Policy interface, registry, two controllers
    scenarios/          Versioned, seeded scenario generation
    runners/            Episode execution
    metrics/            Metric computation + statistics + comparison
    graders/            Automated outcome classification
    artifacts/          Episode artifact storage
    adapters/           Simulator adapter contract
    tests/              Simulation tests
  frontend/
    src/
      api/              Typed REST client
      components/       Layout, panels, badges, states
      hooks/            Async data + polling hooks
      lib/              Formatting helpers
      pages/            Overview, Tasks, New, Details, Compare, Episode
      types/            API contract types
    package.json        React + Vite + Tailwind
  configs/              Example configurations and scenario suites
  datasets/             Dataset manifests (binaries git-ignored)
  scripts/              smoke_sim.py, smoke_e2e.py, benchmark.py, demo_m2/m3/m4.py,
                        run_api.sh, dev.sh
  docs/                 architecture, evaluation-methodology, data-model,
                        benchmarking, limitations, research-log, troubleshooting
  Dockerfile            Multi-stage image (frontend + backend, one origin)
  docker-compose.yml    Single-service stack + optional PostgreSQL profile
  .github/workflows/    CI (backend + frontend)
```

Simulation logic is intentionally kept independent of HTTP endpoints and UI
components so it can be tested and reused without the backend or frontend.

## Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| M1 | Scaffold, tooling, CI, headless MuJoCo smoke test | **Complete** |
| M2 | Reach environment, policy interface, two controllers, seeded scenarios | **Complete** |
| M3 | Episode runner, metrics, grader, artifact persistence, tests | **Complete** |
| M4 | Experiment API, worker lifecycle, DB persistence, reproducibility | **Complete** |
| M5 | Statistical comparison and regression detection | Not started |
| M6 | React dashboard (overview, new evaluation, details, compare, inspector) | **Complete** |
| M7 | Docker, docs, end-to-end verification | **Complete** |
| M8 | Optional vision / learned-policy extension | Not started |

## Known limitations

- The dashboard is complete for the evaluation workflow, but the **episode
  inspector does not yet plot per-step trajectories**: the artifact endpoint
  returns array shapes only, so no time-series or replay is shown. This is
  deliberate — the UI does not invent trajectory data. An array-content endpoint
  and plotting are a follow-up.
- The comparison view surfaces confidence intervals and verdicts (M5), but with
  small suites the verdict will read **INCONCLUSIVE**; interpret accordingly.
- The worker is a **single-process, single-threaded bounded local executor**. It
  is correct and restart-safe, but not horizontally scalable.
- SQLite is used by default; PostgreSQL compatibility is intended but not yet
  exercised in CI.
- The dashboard has **no authentication**; do not expose it to untrusted
  networks.
- Both policies are deterministic classical controllers. There is **no learned
  policy** yet; do not read the baseline/candidate comparison as a model-quality
  claim.
- Collision means EE-vs-floor contact, which is exact for this model because
  only the end effector and floor are collidable. It is not a general collision
  metric for arbitrary scenes.
- The reach task is a self-authored kinematic 4-DOF task, not a benchmark. Its
  difficulty tiers are heuristic and may not be uniformly calibrated.
- Rendering requires an external GL backend and is not exercised in CI unless a
  backend is installed.
- Targets are sampled in an empirically estimated reachable shell; a few
  generated hard cases are near the workspace boundary and may be unreachable by
  either controller.
- Throughput and latency are single-process CPU measurements and are not
  performance guarantees.

## Reproducing the demo

Everything above is reproducible from a clean checkout:

```bash
git clone <repo> && cd simeval
make venv && make install && make dev-deps
make migrate
make e2e                       # complete workflow, isolated temp DB, exit 0 on success
make benchmark                 # regenerate docs/benchmarking.md on your hardware
make smoke                     # headless simulator capability probe
docker compose up --build      # single-container UI + API on http://localhost:8000
```

Determinism is verified by the test suite: a fixed scenario + policy +
configuration reproduces the same episode, and covered scenarios reproduce
across process restarts. Cross-platform (CPU/OS/MuJoCo-version) determinism is
**not** guaranteed.

## Future directions

- Expose per-step artifact **contents** so the episode inspector can plot real
  trajectories, action traces, and contact events (no invented data).
- Broaden the task suite (contact-rich manipulation, grasping) and add a
  MuJoCo-Menagerie / ManiSkill adapter behind the existing simulator boundary.
- Grow held-out suites and add sequential/group-sequential stopping rules so
  comparisons reach an evidence verdict with fewer episodes.
- Add a learned or vision-based policy with a documented, reproducible training
  and evaluation pipeline (Milestone 8), and evaluate it against the classical
  baselines on identical scenarios.
- Optional object-storage artifact backend and PostgreSQL in CI.

## License

Apache-2.0. The MJCF models in `scripts/smoke_sim.py` and
`simulation/environments/reach_mjcf.py` are authored for this project and carry
no third-party licensing restrictions.
