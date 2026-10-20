# Architecture

Status: reflects **Milestones 1–6**.

## 1. Layering

```
simulation/            Pure simulation + evaluation (no HTTP, no DB)
  environments/        MJCF models, reach env, task spec, kinematics
  policies/            Policy interface, registry, controllers
  scenarios/           Versioned, seeded scenario generation
  runners/             Episode execution, trace recording, outcome types
  metrics/             Metric computation over episode results
  graders/             Deterministic outcome classification
  artifacts/           Artifact store abstraction + local .npz store
  adapters/            (reserved) simulator adapter contract

backend/app/           HTTP + persistence + orchestration
  core/                settings, logging
  db/                  engine, session, base
  models/              SQLAlchemy ORM entities
  schemas/             Pydantic request/response models
  services/            state machine, experiment service, suite service, registry sync
  workers/             bounded local experiment worker
  api/                 FastAPI routers
  main.py              app factory + lifespan

frontend/              React dashboard (Milestone 6)
  src/api/             typed REST client (only network boundary in the UI)
  src/hooks/           async + polling hooks with loading/error state
  src/components/      layout, panels, badges, states
  src/pages/           Overview, Tasks, New, Details, Compare, Episode
  src/types/           API contract types
```

**Rule:** `simulation/` must never import `backend/`. The backend depends on the
simulation package, never the reverse. This keeps the evaluation engine testable
and reusable without HTTP or a database. The single coupling point is
`backend/app/services/registry_sync.py`, which reads the policy registry and the
default task spec to seed the database.

**Frontend rule:** the dashboard reads exclusively through `src/api/client.ts`
against `/api/v1`. It neither imports backend internals nor maintains a separate
fake data model. In development the Vite dev server proxies `/api` to the
backend; CORS is enabled on the backend for direct browser access.

## 2. Request / execution flow

```
POST /experiments            -> experiment_service.create_experiment  (QUEUED, persisted)
POST /experiments/{id}/start -> worker.submit(id)
worker thread:
   transition RUNNING
   load suite payload + policy config + eval config from DB
   for each scenario (split-filtered):
     run_episode(...) -> EpisodeResult (real MuJoCo + trace + artifact)
     persist Episode row
   aggregate metrics -> Experiment.metrics
   transition COMPLETED
GET /experiments/{id}        -> persisted status/metrics
GET /experiments/{id}/episodes -> persisted rows
GET /episodes/{id}/artifacts -> artifact store read
```

State is persisted **before** execution begins (the experiment row exists in
QUEUED before the worker ever sees it). The worker checks the cancellation flag
between episodes so cancellation is honoured promptly.

## 3. Core design decisions

### Simulator adapter boundary
The environment exposes a small contract (`reset`, `step`, observation dict,
ground-truth accessors, `kinematics_context`). The runner depends on this
contract, not on MuJoCo directly, except for the artifact/observation shapes.
`simulation/adapters/` is reserved for formalising a multi-simulator contract in
a later milestone; it is intentionally empty rather than prematurely abstracted.

### Policies output joint setpoints, not torques
The MJCF uses position servos, so the action space is desired joint positions.
This keeps the action contract stable and lets both classical controllers and
(future) learned policies share the interface.

### Infrastructure vs task failure
The grader separates platform failures (`SIMULATOR_ERROR`, `INVALID_ACTION`,
`NUMERICAL_FAILURE`) from task failures. Metric denominators exclude
infrastructure failures by default. This prevents a broken simulator from being
misread as a bad policy.

### Bounded local worker, not distributed infra
A single-threaded bounded executor is sufficient to measure and produces
reproducible results without Ray/Kafka/Kubernetes. Distributed orchestration is
deferred until measurements justify it.

### Persist structured data, not arrays
Episode rows store scalars and a JSON metric map; per-step arrays live in
compressed `.npz` artifacts addressed by relative keys. This keeps the database
small and the artifact store swappable.

## 4. Rejected alternatives

* **Storing trajectory arrays in the database** — rejected for size and query
  cost; artifacts are addressed by key.
* **Auto-starting experiments on create** — rejected; creation persists QUEUED
  and an explicit `/start` decouples configuration review from execution.
* **In-process threads per experiment with unbounded concurrency** — rejected;
  the frontend must not be able to spawn unlimited simulations.
* **Fabricating a "success" on timeout** — rejected by construction; the runner
  and grader never count a timeout or crash as success.

## 5. Restart safety

On startup the worker calls `recover_interrupted()`: experiments left RUNNING by
a previous process are requeued (or cancelled if a cancellation was requested).
Verified by `backend/tests/test_worker.py` and the M4 demo. Persistence across
restarts is verified by `test_api.py::test_experiment_persistence_across_restart`.

## 6. Known gaps (see docs/limitations.md)

* No statistics / confidence intervals (M5).
* No authentication or multi-user isolation.
* No distributed workers.
* SQLite default; PostgreSQL compatibility intended, not CI-tested.
