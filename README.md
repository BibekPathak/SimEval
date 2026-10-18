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

# 4. Run the quality gates
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
    environments/       MJCF models, reach task, env, kinematics
    policies/           Policy interface, registry, two controllers
    scenarios/          Versioned, seeded scenario generation
    runners/            Episode execution
    metrics/            Metric computation
    graders/            Automated outcome classification
    artifacts/          Episode artifact storage
    adapters/           Simulator adapter contract
    tests/              Simulation tests
  frontend/             React + TypeScript dashboard        (later milestones)
  configs/              Example configurations and scenario suites
  datasets/             Dataset manifests (binaries git-ignored)
  scripts/              Developer scripts (smoke_sim.py, demo_m2.py)
  docs/                 Technical documentation
  .github/workflows/    CI
```

Simulation logic is intentionally kept independent of HTTP endpoints and UI
components so it can be tested and reused without the backend or frontend.

## Roadmap

| Milestone | Scope | Status |
|-----------|-------|--------|
| M1 | Scaffold, tooling, CI, headless MuJoCo smoke test | **Complete** |
| M2 | Reach environment, policy interface, two controllers, seeded scenarios | **Complete** |
| M3 | Episode runner, metrics, grader, artifact persistence, tests | Not started |
| M4 | Experiment API, worker lifecycle, DB persistence, reproducibility | Not started |
| M5 | Statistical comparison and regression detection | Not started |
| M6 | React dashboard (overview, new evaluation, details, compare, inspector) | Not started |
| M7 | Docker, docs, end-to-end verification | Not started |
| M8 | Optional vision / learned-policy extension | Not started |

## Known limitations

- The environment, two policies, and scenario generation exist, but there is no
  episode runner, metric computation, grader, persistence, or API yet. Success
  counts in the M2 demo are simple booleans, not the full metric set.
- Both policies are deterministic classical controllers. There is **no learned
  policy** yet; do not read the baseline/candidate comparison as a model-quality
  claim.
- The reach task is a self-authored kinematic 4-DOF task, not a benchmark. Its
  difficulty tiers are heuristic and may not be uniformly calibrated.
- Rendering requires an external GL backend and is not exercised in CI unless a
  backend is installed.
- Targets are sampled in an empirically estimated reachable shell; a few
  generated hard cases are near the workspace boundary and may be unreachable by
  either controller.

## License

Apache-2.0. The MJCF models in `scripts/smoke_sim.py` and
`simulation/environments/reach_mjcf.py` are authored for this project and carry
no third-party licensing restrictions.
