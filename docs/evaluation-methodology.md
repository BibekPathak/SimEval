# Evaluation Methodology

This document defines how SimEval executes episodes, grades them, and computes
metrics. It is the authoritative reference for what each number means. Any
change to these definitions is a change to the evaluation protocol and should be
recorded in `docs/research-log.md`.

Status: reflects **Milestones 1–3**. Statistical inference (confidence
intervals, paired comparisons, regression thresholds) is defined in Milestone 5
and is **not yet implemented**; this document marks those gaps explicitly.

## 1. Unit of evaluation

* **Scenario** — a fully specified initial condition (seed, target pose, initial
  posture, split). Scenarios are the unit for paired comparison later.
* **Episode** — one execution of one policy on one scenario.
* **Timestep** — a single MuJoCo `mj_step`. Timesteps are **not** independent
  samples and must never be treated as such for inference.

The same scenario + same policy + same configuration must produce the same
episode (verified by tests and the M2/M3 demos).

## 2. Episode lifecycle

1. Build the environment (4-DOF reach task) and the policy.
2. `reset(seed=scenario.seed)` with the scenario's initial posture and noise.
3. Loop up to `max_steps` (400) control steps:
   * optional wall-clock timeout check,
   * policy produces an action (desired joint positions),
   * action validated for shape and finiteness, then clipped to joint limits,
   * simulation steps, trace recorded, metrics accumulated,
   * stop on termination (sustained success), truncation (budget/timeout), or a
     hard error (non-finite action/state).
4. Persist the recorded trace as a compressed `.npz` artifact.
5. Grade the episode from recorded evidence.
6. Return an `EpisodeResult`.

The environment is always closed in a `finally` block. A crash or timeout is
**never** counted as a successful task.

### Termination and truncation

* **Termination (success):** the end effector stays within
  `success_distance_m` (0.05 m) of the target for `success_dwell_steps` (10)
  consecutive steps. The dwell window prevents counting a transient fly-through
  as success.
* **Truncation:** the step budget is exhausted, or the optional wall-clock
  timeout fires. Truncation alone is a task failure unless success already
  occurred.
* **Hard errors:** non-finite action or non-finite recorded state end the episode
  immediately as an **infrastructure** failure.

## 3. Outcome categories

| Category | Class | Meaning |
|----------|-------|---------|
| `SUCCESS` | task | Success condition met and terminated. |
| `TIMEOUT` | task | Step budget exhausted without success. |
| `TARGET_NOT_REACHED` | task | Ended early, no success, no collision, no timeout. |
| `COLLISION` | task | EE contacted the floor before reaching the target. |
| `INVALID_ACTION` | infrastructure | Policy emitted a non-finite action. |
| `NUMERICAL_FAILURE` | infrastructure | Non-finite state observed during the episode. |
| `SIMULATOR_ERROR` | infrastructure | An exception was raised during execution. |
| `OTHER_FAILURE` | task | No rule matched. |

**Task failures** are evidence about the policy. **Infrastructure failures** are
evidence about the platform and are excluded from policy-quality denominators by
default. The grader (`simulation/graders/reach_grader.py`) encodes this
precedence and is unit-tested without a simulator.

## 4. Metric definitions

Reported by `simulation/metrics/reach_metrics.py` over persisted
`EpisodeResult`s.

| Metric | Definition | Units | Aggregation | Limitation |
|--------|-----------|-------|-------------|-----------|
| `success_rate` | successful / evaluated episodes | ratio | mean | treats episodes as independent; correlated within a scenario |
| `failure_rate` | 1 − success_rate | ratio | mean | — |
| `completion_time_*` | steps × timestep for **successful** episodes | s | mean, median | undefined for failures; failures are excluded, not zero |
| `episode_length_*` | control steps executed | steps | mean | timeouts are `max_steps` by construction |
| `collision_rate` | episodes with ≥1 EE-floor contact step | ratio | mean | EE-floor contact only |
| `mean_collision_steps` | mean steps with ≥1 EE-floor contact | steps | mean | — |
| `return_mean/median` | sum of rewards | reward | mean, median | sparse terminal reward → 1 on success else 0 |
| `throughput_eps_per_s` | evaluated episodes / wall-clock | eps/s | ratio | machine-load sensitive |
| `mean_wall_clock_s` | per-episode wall-clock | s | mean | includes overhead |
| `mean_policy_inference_ms` | policy `act` latency | ms | mean | cold-start included |

For success rate, the numerator (`n_success`) and denominator
(`n_episodes_evaluated`) are always reported alongside the ratio.

### Contact vs. collision

"Collision" here is defined as **end-effector vs. floor contact**. This is exact
for the reach task because the MJCF model makes only the EE sphere and the floor
collidable (arm links are deliberately non-colliding to avoid spurious
self-collision drift). It is **not** a general-purpose collision count for
arbitrary scenes.

## 5. Reproducibility

* Scenario suites are versioned and content-hashed. The same hash implies the
  same scenarios.
* Episodes reset from the scenario seed with `qpos_noise` (0 by default), so
  resets are bit-reproducible.
* Policies are deterministic; the runner records the policy name and version.
* The M2/M3 demos were confirmed to reproduce identical success counts across
  independent process runs.

## 6. What is not yet claimed

* No confidence intervals are reported (Milestone 5).
* No paired scenario-level comparison or regression thresholds (Milestone 5).
* No claim of statistical significance anywhere.
* No GPU acceleration; all timings are single-process CPU measurements.
* No learned policy; both policies are deterministic classical controllers.

## 7. Data provenance

Every metric is derived from persisted episode artifacts and results. Fixture
data used in unit tests is clearly separated from real simulation runs:
grader and metric tests construct synthetic `EpisodeResult`s directly and never
masquerade as simulator output, while runner tests execute real MuJoCo rollouts.
