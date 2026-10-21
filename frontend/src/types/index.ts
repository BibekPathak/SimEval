// TypeScript types mirroring the backend Pydantic schemas (backend/app/schemas).
// The frontend consumes the REST API only; these types are the contract.

export interface HealthResponse {
  status: string;
  app_name: string;
  version: string;
  database: string;
  worker: {
    running: boolean;
    current_experiment: string | null;
    queue_depth: number;
    max_concurrent_experiments: number;
  };
}

export interface TaskOut {
  name: string;
  version: string;
  description: string | null;
  spec: Record<string, unknown>;
}

export interface PolicyOut {
  name: string;
  version: string;
  description: string | null;
  default_config: Record<string, unknown>;
}

export interface SuiteSummaryOut {
  suite_name: string;
  suite_version: string;
  task_name: string;
  task_version: string;
  content_hash: string;
  n_scenarios: number;
  counts: Record<string, number>;
  created_at: string | null;
}

export interface SuiteDetailOut extends SuiteSummaryOut {
  generator: Record<string, unknown>;
  payload: {
    scenarios?: ScenarioPayload[];
    [k: string]: unknown;
  };
}

export interface ScenarioPayload {
  scenario_id: string;
  task_name: string;
  task_version: string;
  seed: number;
  target_position: number[];
  initial_qpos: number[] | null;
  qpos_noise: number;
  difficulty: string;
  split: string;
  metadata: Record<string, unknown>;
}

export type ExperimentStatus =
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export interface ExperimentSummaryOut {
  experiment_id: string;
  name: string;
  policy_name: string;
  policy_version: string;
  task_name: string;
  task_version: string;
  suite_name: string;
  suite_version: string;
  suite_hash: string;
  split: string;
  status: ExperimentStatus;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  metrics: Record<string, unknown>;
}

export interface ExperimentDetailOut extends ExperimentSummaryOut {
  description: string | null;
  policy_config: Record<string, unknown>;
  seeds: Record<string, unknown>;
  eval_config: Record<string, unknown>;
  code_revision: string | null;
  runtime_metadata: Record<string, unknown>;
  dataset_version: string | null;
  error: string | null;
  cancellation_requested: boolean;
}

export interface EpisodeOut {
  episode_id: string;
  experiment_id: string;
  scenario_id: string;
  policy_name: string;
  policy_version: string;
  task_name: string;
  task_version: string;
  seed: number;
  split: string;
  difficulty: string;
  success: boolean;
  outcome: string;
  failure_category: string | null;
  explanation: string;
  rule: string;
  steps: number;
  wall_clock_s: number;
  sim_time_s: number;
  return_sum: number;
  initial_ee_target_dist_m: number;
  final_ee_target_dist_m: number;
  min_ee_target_dist_m: number;
  collision_steps: number;
  max_collision_count: number;
  policy_inference_s: number;
  metrics: Record<string, unknown>;
  artifact_ref: string | null;
  error: string | null;
}

export interface EpisodeArtifactsOut {
  episode_id: string;
  artifact_ref: string | null;
  exists: boolean;
  arrays: Record<string, number[]>;
}

export interface ArtifactSeriesOut {
  episode_id: string;
  artifact_ref: string;
  exists: boolean;
  n_steps: number;
  stride: number;
  returned_steps: number;
  series: Record<string, number[] | number[][]>;
}

export interface MetricSet {
  n_episodes_total: number;
  n_episodes_evaluated: number;
  n_infrastructure_failures: number;
  n_success: number;
  success_rate: number | null;
  failure_rate: number | null;
  completion_time_mean_s: number | null;
  completion_time_median_s: number | null;
  episode_length_mean_steps: number | null;
  collision_rate: number | null;
  mean_collision_steps: number | null;
  return_mean: number | null;
  return_median: number | null;
  throughput_eps_per_s: number | null;
  mean_wall_clock_s: number | null;
  mean_policy_inference_ms: number | null;
  failure_categories: Record<string, number>;
}

export interface ComparisonMetric {
  metric: string;
  unit: string;
  direction: string;
  a: number | null;
  b: number | null;
  delta: number | null;
  relative: number | null;
  ci_low: number | null;
  ci_high: number | null;
  confidence: number;
  method: string;
  n_pairs: number;
  verdict: "IMPROVED" | "REGRESSED" | "INCONCLUSIVE" | "MISSING";
  reason: string;
}

export interface CompareOut {
  a: string;
  b: string;
  compatible: boolean;
  warnings: string[];
  n_scenarios_a: number;
  n_scenarios_b: number;
  shared_scenarios: number;
  metrics: ComparisonMetric[];
  failure_category_delta: Record<string, number>;
  sufficient_evidence: boolean;
  summary: string;
}

export interface ExperimentCreateIn {
  name: string;
  description?: string | null;
  policy_name: string;
  policy_config?: Record<string, unknown> | null;
  task_name?: string;
  task_version?: string;
  suite_name: string;
  suite_version: string;
  split?: string;
  dataset_version?: string | null;
  seed?: number | null;
  capture_every?: number;
  persist_artifacts?: boolean;
  timeout_s?: number | null;
  code_revision?: string | null;
}

export interface SuiteCreateIn {
  suite_name: string;
  suite_version?: string;
  task_name?: string;
  task_version?: string;
  n_scenarios?: number;
  base_seed?: number;
  dev_frac?: number;
  val_frac?: number;
  qpos_noise?: number;
}

export interface DataTableSort<K extends string> {
  key: K;
  dir: "asc" | "desc";
}
