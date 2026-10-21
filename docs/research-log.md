# Research Log

Chronological record of hypotheses, experiments, results, failed approaches, and
next steps. Newest milestones at the bottom.

## M1 — Scaffold + headless simulator probe

**Goal:** verify real headless MuJoCo before building anything on top.

- Confirmed MuJoCo 3.16 installs and steps real physics headlessly.
- Rendering: no OSMesa/EGL on the dev machine, but `MUJOCO_GL=glfw` renders
  successfully. Rendering is therefore treated as **optional**; evaluation never
  depends on it.
- Built `scripts/smoke_sim.py` as a real capability probe (seeded reset, stepping,
  determinism, geometry, contacts).
- Failed approach: an initial hand-tuned controller drove the EE *away* from the
  target (wrong sign/axis). Fixed by using the real site Jacobian.
- Failed approach: a straight-arm start pose was singular; fixed by starting the
  arm in a bent (non-singular) configuration.
- Failed approach: `link1_g` penetrated `base_g`, injecting spurious yaw drift.
  Fixed by making arm links non-colliding (`contype=0 conaffinity=0`); recorded
  as a documented modeling decision.
- Result: deterministic rollout (0.0 diff over 400 steps), EE reaches target
  exactly, bit-identical across processes.

## M2 — Environment, policies, scenarios

**Goal:** a real task with two meaningfully different policies and reproducible
scenarios.

- Extended the model to a 4-DOF arm (added a wrist joint) for a richer reach task.
- Two strategies: **global IK setpoint planner** (baseline) vs. **incremental
  resolved-rate controller** (candidate). Documented that these differ in
  algorithm, not merely parameters.
- Failure discovered: with naive targets both policies scored 30/30 — no
  discrimination. Added adversarial initial postures for medium/hard tiers,
  producing genuine failure signal (baseline 26/30, candidate 25/30 on n=30).
- Result: deterministic suites with content hashes, split isolation verified,
  both policies control the sim and fail on the hardest cases.

## M3 — Runner, metrics, grader, artifacts

**Goal:** a trustworthy, evidence-backed evaluation pipeline.

- Trace recording captures real per-step state; metrics derive from persisted
  episodes, not recomputation.
- Grader separates task vs. infrastructure failures; verified by tests that a
  NaN policy is `INVALID_ACTION` and an env failure is `SIMULATOR_ERROR`, neither
  counted as success.
- Failed approach: environment construction happened outside the runner's
  try/except, so an engine error escaped instead of being graded. Fixed by
  constructing inside the try with a guarded `finally` close.
- Observation: the candidate controller is slower (mean ~246 steps vs ~101) with
  similar success — a real speed/robustness tradeoff, reported as-is rather than
  as an "improvement". This motivates M5's uncertainty-aware comparison.

## M4 — Experiment API, worker, persistence, reproducibility

**Goal:** persist experiments, run them via a bounded worker, and reproduce.

- SQLAlchemy models + Alembic migration verified to upgrade *and* downgrade.
- Enforced state machine; invalid transitions raise (e.g. cannot cancel a
  COMPLETED experiment).
- Worker recovery: a RUNNING experiment left by a dead process is requeued (or
  cancelled if flagged). Verified by test.
- Failed approach: the FastAPI validation handler returned Pydantic `errors()`
  containing a raw `ValueError` in `ctx`, which was not JSON-serializable and
  500'd. Fixed by sanitising `ctx`.
- Failed approach: importing `episode_runner` from the `runners` package
  `__init__` created an import cycle with the grader. Fixed by keeping
  `runners/__init__` lightweight and importing the runner module directly.
- Result: full lifecycle (create → start → COMPLETED with metrics, episodes,
  artifacts), compare, reproduce, and persistence across restart all verified
  end to end against a real uvicorn server and the TestClient.

## M5 — Statistical comparison and regression detection

**Goal:** answer whether an apparent improvement is meaningful, without
over-claiming.

- Methods: **Wilson score interval** for per-arm success rates and the paired
  success-rate difference; **paired bootstrap** over scenario differences for
  continuous metrics. Scenario is the resampling unit; timesteps are never
  treated as independent samples.
- Verdicts are direction-aware (`higher_is_better` / `lower_is_better`): a metric
  is `IMPROVED`/`REGRESSED` only when the paired 95% interval excludes zero **and**
  the effect clears a per-metric threshold; otherwise `INCONCLUSIVE`. Below a
  minimum of 10 paired scenarios the report is explicitly "insufficient evidence".
- Infrastructure failures are excluded from paired comparisons; they are not
  evidence about policy quality.
- Observation on the real data: the candidate controller reaches similar success
  but takes markedly longer (mean ~250 steps vs ~100). With 12 shared scenarios
  the comparison flags `episode_length_mean_steps` and `completion_time_mean_s`
  as **REGRESSED** and success rate **INCONCLUSIVE** — an honest result, not a
  win.
- Fixed during this milestone: mypy flagged `Interval` optional fields and
  ndarray arguments; the bootstrap signature now accepts array-likes and the
  tests narrow optionals explicitly. mypy is clean across the repo.

## M6 — React dashboard

**Goal:** a usable, professional research tool over the real API.

- Vite + React 18 + TypeScript + Tailwind. Data flows only through a typed REST
  client; nothing is mocked. A Vite dev proxy avoids CORS in development (CORS is
  also enabled on the backend).
- Pages: Overview, Tasks & Suites, New Evaluation, Experiment details, Compare,
  Episode inspection.
- The Compare page surfaces the M5 report directly (deltas, 95% intervals,
  verdicts, per-arm Wilson intervals, evidence flag, compatibility warnings).
- Honesty constraint honored: the episode inspector shows the grader's deciding
  rule, recorded scalars, and artifact **array shapes**, but deliberately does
  **not** plot trajectories, because the artifacts endpoint returns only shapes.
  Plotting awaits an array-content endpoint. No invented data is displayed.
- Verified in a real browser against a live backend: overview counts, the
  regression-flagged comparison, the episode table with sorting/filtering, the
  artifact shapes, and a create-and-start flow that polls RUNNING → COMPLETED.
- Failed approach: `tsc` rejected `import.meta.env` and `__dirname`; fixed with a
  `vite-env.d.ts`, `@types/node`, and an ESM-safe `import.meta.url` alias.

## M7 — Packaging, end-to-end verification, benchmarks, docs

**Goal:** make the system reproducible and demonstrable.

- Multi-stage Docker image (frontend build + headless backend served from one
  origin, SPA fallback with reserved `/api`, `/docs`, `/redoc`, `/openapi.json`).
- `scripts/smoke_e2e.py` drives the whole workflow on an isolated temp DB, and
  `scripts/dev.sh` starts backend + dashboard together.
- `scripts/benchmark.py` measures the real pipeline; numbers written to
  `docs/benchmarking.md`. Measured ~12.6 eps/s at `capture_every=1`, 5.5×
  real-time factor, ~69 ms/episode policy inference.
- Verified by building and running the Docker image and completing a real
  10-scenario experiment **inside the container** (9/10 success, artifacts
  persisted).

## M8 — Learned policy (behavior cloning with DAgger)

**Goal:** one well-scoped learned policy with a reproducible pipeline.

- Constraint: the environment has <1 GB free disk, so a multi-gigabyte deep
  learning framework is not installable. Chose a self-contained **NumPy MLP**
  (12→64→64→4) with a real forward pass, backpropagation, Adam, a
  train/validation split, and early stopping. Documented as a deliberate
  tradeoff, not a general DL stack.
- Data provenance: demonstrations are generated by *this project* from real
  MuJoCo rollouts of the deterministic expert, with a manifest, schema version,
  and SHA-256 checksum. No third-party data.
- **Central finding — plain BC fails.** Single-step behavior cloning of the
  expert achieved **0/16** on held-out scenarios despite low supervised loss.
  Diagnosed as classic compounding error: the policy was trained only on
  expert-visited states, saturated the joint limits within one step, and never
  learned to recover. (Verified by tracing the per-step action error.)
- Also tried imitating the smoother incremental controller — still 0/X. The
  problem is the state distribution, not the expert's smoothness.
- **Fix — DAgger.** Implemented Dataset Aggregation: choose the expert with
  probability β (1.0 → 0.5), otherwise the learner; label every visited state
  with the expert action; aggregate all data; retrain each iteration. Held-out
  success rose from 0% to **83.9% (26/31)**.
- Final held-out comparison: expert 28/31 (90.3%), DAgger-learned 26/31 (83.9%),
  mean length 80 vs 141 steps. The learned policy recovers most of the gap but is
  slower; remaining failures are `TIMEOUT` on hard boundary scenarios.
- Ablation: disabling joint-limit clamping changed nothing (26/31 both ways) —
  reported as a negative result rather than spun as an improvement.
- The learned policy is registered (`behavior_cloning`) and runs end-to-end
  through the API/worker like any other policy (verified: 6/8 on a small suite).

## Next steps

- Add an artifact **array-content** endpoint so the episode inspector can plot
  real per-step time-series (state vs. target, action traces, contacts).
- Scale DAgger (more iterations/scenarios) and add a learned-policy comparison
  with confidence intervals once suites are large enough to be informative.
- Explore a small **vision** policy (target detection / visual state estimation)
  with a documented dataset and perception-to-action loop.
- Revisit the candidate vs. baseline tradeoff with larger suites before any
  performance claim.
