# Data Model

SimEval separates three kinds of data:

1. **Configuration** — declarative, versioned definitions (task spec, scenario
   suites, policy configs). Serialized as JSON.
2. **Structured results** — per-episode and per-experiment records. Destined for
   the relational database (Milestone 4); currently represented as dataclasses
   that serialize to JSON.
3. **Artifacts** — larger per-step arrays written to an artifact store, never as
   database rows.

Status: reflects **Milestones 1–8**. The database schema and SQLAlchemy models
are introduced in Milestone 4; this document defines the logical shapes they
must implement.

## 1. Task specification

`simulation/environments/reach_task.py` — `ReachTaskSpec` (frozen):

* `task_name`, `task_version`
* `success_distance_m`, `success_dwell_steps`
* `max_steps`, `timestep_s`
* `collision_is_floor_contact`

Changing any of these is a task-version change and invalidates comparisons
across versions.

## 2. Scenario

`simulation/scenarios/generator.py` — `Scenario` (frozen):

| Field | Type | Notes |
|-------|------|-------|
| `scenario_id` | str | stable identity |
| `task_name`, `task_version` | str | task binding |
| `seed` | int | drives reset randomness |
| `target_position` | [float;3] | goal pose (m) |
| `initial_qpos` | [float;nq] or null | starting posture |
| `qpos_noise` | float | per-joint reset noise (0 = deterministic) |
| `difficulty` | enum | `easy`, `medium`, `hard` |
| `split` | enum | `dev`, `validation`, `held_out` |
| `metadata` | object | generation metadata |

`ScenarioSuite` groups scenarios with a `suite_version` and a content hash. The
suite hash is the reproducibility handle experiments record.

**Split discipline:** split is assigned deterministically from the seed, so a
logical scenario is in exactly one split. `assert_no_leakage` enforces this.

## 3. Policy configuration

`simulation/policies/base.py` — `PolicyConfig` (frozen) and subclasses
`IKPlannerConfig`, `ResolvedRateConfig`. Each exposes `to_dict()` for
serialization and a `version` string. Experiments store the policy name, version,
and config mapping.

## 4. Episode result (structured, per episode)

`simulation/runners/outcome.py` — `EpisodeResult`:

* identity: `episode_id`, `experiment_id`, `scenario_id`
* policy: `policy_name`, `policy_version`
* task: `task_name`, `task_version`
* scenario context: `seed`, `split`, `difficulty`
* grade: `success`, `outcome`, `failure_category`, `rule`, `explanation`
* aggregates: `steps`, `wall_clock_s`, `sim_time_s`, `return_sum`,
  `initial_ee_target_dist_m`, `final_ee_target_dist_m`, `min_ee_target_dist_m`,
  `collision_steps`, `max_collision_count`, `policy_inference_s`
* references: `artifact_ref`, `error`
* `metrics`: a flexible per-episode metric map

This is the row that Milestone 4's database will store (one row per episode,
indexed by `experiment_id` and `scenario_id`).

## 5. Episode artifact (arrays, per episode)

Written by `simulation/artifacts/store.py` as a compressed `.npz` keyed by
`{experiment_id}/episodes/{episode_id}`. Arrays (schema version `1`):

| Array | Shape | Units |
|-------|-------|-------|
| `source_step` | (T,1) | env step index at capture |
| `qpos` | (T,nq) | rad |
| `qvel` | (T,nq) | rad/s |
| `ee_pos` | (T,3) | m |
| `target_pos` | (T,3) | m |
| `ee_target_dist` | (T,1) | m |
| `action` | (T,nq) | rad |
| `reward` | (T,1) | reward |
| `collision` | (T,1) | contacts |

`T` is the number of captured steps (`capture_every` controls density; the
initial step is always captured). A `__schema_version__` marker is stored but
hidden on read. The store rejects absolute paths and `..` traversal.

## 6. Experiment (structured, per experiment — Milestone 4)

Defined now as a contract; implemented in Milestone 4. An experiment record
will contain: unique id, name/description, policy name/version/config, task and
environment version, scenario-suite version/hash, dataset version (if any),
seeds, evaluation config, code revision, runtime metadata, start/completion
times, status, aggregated metrics, artifact references, and errors.

## 7. Storage rules

* Structured metadata → relational database (Milestone 4). Never store large
  arrays as rows.
* Large arrays → artifact store (`.npz`). References stored alongside episode
  rows.
* No API parameter is ever treated as an absolute filesystem path.
* No user-supplied Python is ever executed.
* Secrets never appear in logs or artifacts.
