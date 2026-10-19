# Limitations

This document is deliberately conservative. SimEval is a research/portfolio
system, not a production deployment, and it does not claim capabilities it has
not implemented or measured.

Status: reflects **Milestones 1–4**.

## Simulation

- Single task family: a self-authored planar 4-DOF reach task. Not a benchmark,
  and not validated against any published environment.
- Difficulty tiers (`easy`/`medium`/`hard`) are heuristic; hard targets near the
  reach boundary can be unreachable by either controller.
- Collision = end-effector vs. floor contact. This is exact for the current MJCF
  (arm links are non-colliding) but is **not** a general collision metric.
- No contact-rich manipulation, grasping, or deformables yet.
- No MuJoCo-Menagerie or ManiSkill integration yet.

## Policies

- Both policies are **deterministic classical controllers** (a full-IK setpoint
  planner and an incremental resolved-rate controller). There is **no learned
  policy**, and no vision/language input. The baseline/candidate comparison is a
  controller comparison, not a model-architecture comparison.
- No imitation-learning or RL training pipeline (Milestone 8, optional).

## Evaluation & statistics

- Metrics are point estimates. **No confidence intervals, no paired bootstrap,
  no significance testing** yet (Milestone 5).
- Comparison is scenario-level in principle but the current endpoint reports
  aggregate deltas and a small-sample warning; it makes **no significance
  claim**.
- Episodes sharing a scenario are correlated and are **not** independent samples.
- No regression thresholds are enforced yet.

## Data

- No dataset manifest/export pipeline yet (Milestone 5/4 data pipeline scope),
  and recorded episodes are **not** claimed to be training-ready.
- Artifacts are stored on the local filesystem only; no object storage backend
  is implemented (the abstraction exists).

## Platform

- The worker is a single-process, single-threaded bounded executor. It is
  restart-safe but not horizontally scalable.
- SQLite by default. PostgreSQL compatibility is intended but not exercised in
  CI.
- No authentication, authorization, or multi-tenant isolation. Do not expose the
  API to untrusted networks.
- No rate limiting beyond bounded worker concurrency.
- Throughput/latency figures are single-process CPU measurements, not
  performance guarantees.
- Rendering requires an external GL backend (glfw/egl/osmesa) and is optional;
  it is not required for evaluation and may be unavailable in headless CI.

## Reproducibility scope

- Determinism is verified for a fixed scenario + policy + configuration within
  documented tolerances, and across process restarts for persisted results.
- Cross-platform determinism (different CPU/OS/MuJoCo versions) is **not**
  guaranteed.
