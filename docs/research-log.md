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

## Next steps

- **M5** statistical comparison: scenario-level pairing, Wilson/binomial CIs for
  success rate, paired bootstrap for continuous metrics, configurable regression
  thresholds, and an explicit "insufficient evidence" verdict.
- **M6** dashboard consuming the `/api/v1` endpoints.
- Revisit the candidate vs. baseline tradeoff with proper uncertainty before any
  claim about improvement.
