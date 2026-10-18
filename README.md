# SimEval — Simulation-Driven Robot Learning Evaluation Platform

> **Status: Milestone 1 complete.** This repository currently contains the
> project scaffold, developer tooling, CI, and a verified **headless MuJoCo
> simulation smoke test**. The evaluation engine, policies, experiment
> management, statistics, API, and dashboard are implemented in later
> milestones (see [Roadmap](#roadmap)).

SimEval is an evaluation-first platform for measuring the performance,
robustness, and generalization of robot-learning policies in simulation. The
central question it answers is:

> **Did this policy actually improve, under which conditions, and what evidence
> supports that conclusion?**

This is a research/portfolio-grade system, not a production deployment. Every
metric is intended to be traceable to real recorded episode data. Simulator
results, unit-test fixtures, and synthetic data are kept explicitly separate,
and no benchmark numbers or improvements are ever fabricated.

## What works today (Milestone 1)

- Repository layout separating simulation, backend, and frontend concerns.
- Pinned Python tooling (`ruff`, `mypy`, `pytest`) with a `Makefile`.
- A **real** MuJoCo capability probe, `scripts/smoke_sim.py`, that:
  - parses a self-authored MJCF 3-DOF reach model,
  - resets with an explicit seed and steps real physics,
  - verifies bit-for-bit determinism across repeated rollouts,
  - reads ground-truth end-effector/target geometry and contact counts,
  - optionally renders an offscreen frame when a GL backend is available.
- GitHub Actions CI running lint, format check, type check, tests, and the
  headless smoke test.

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

# 3. Run the quality gates
make lint
make typecheck
make test
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
  backend/app/          FastAPI app, DB, services, workers   (later milestones)
  backend/tests/        Backend tests
  simulation/
    environments/       MJCF task environments
    policies/           Policy interface and controllers
    scenarios/          Versioned, seeded scenario generation
    runners/            Episode execution
    metrics/            Metric computation
    graders/            Automated outcome classification
    artifacts/          Episode artifact storage
    adapters/           Simulator adapter contract
    tests/              Simulation tests
  frontend/             React + TypeScript dashboard        (later milestones)
  configs/              Example configurations
  datasets/             Dataset manifests (binaries git-ignored)
  scripts/              Developer scripts (smoke_sim.py)
  docs/                 Technical documentation
  .github/workflows/    CI
```

Simulation logic is intentionally kept independent of HTTP endpoints and UI
components so it can be tested and reused without the backend or frontend.

## Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| M1 | Scaffold, tooling, CI, headless MuJoCo smoke test | **Complete** |
| M2 | Reach environment, policy interface, two controllers, seeded scenarios | Not started |
| M3 | Episode runner, metrics, grader, artifact persistence, tests | Not started |
| M4 | Experiment API, worker lifecycle, DB persistence, reproducibility | Not started |
| M5 | Statistical comparison and regression detection | Not started |
| M6 | React dashboard (overview, new evaluation, details, compare, inspector) | Not started |
| M7 | Docker, docs, end-to-end verification | Not started |
| M8 | Optional vision / learned-policy extension | Not started |

## Known limitations

- Only the simulation capability probe exists; there is no evaluation pipeline
  or API yet.
- Rendering requires an external GL backend and is not exercised in CI unless a
  backend is installed.
- The smoke-test model is a self-authored kinematic reach task for capability
  verification, not a benchmark.

## License

Apache-2.0. The MJCF model in `scripts/smoke_sim.py` is authored for this
project and carries no third-party licensing restrictions.
