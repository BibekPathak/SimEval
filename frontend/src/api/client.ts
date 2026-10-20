// REST client for the SimEval backend. All dashboard data comes through here;
// the UI never mocks data or imports backend internals.

import type {
  CompareOut,
  EpisodeArtifactsOut,
  EpisodeOut,
  ExperimentCreateIn,
  ExperimentDetailOut,
  ExperimentSummaryOut,
  HealthResponse,
  MetricSet,
  PolicyOut,
  SuiteCreateIn,
  SuiteDetailOut,
  SuiteSummaryOut,
  TaskOut,
} from "@/types";

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => null);
    }
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  const search = new URLSearchParams(entries.map(([k, v]) => [k, String(v)]));
  return `?${search.toString()}`;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  tasks: () => request<TaskOut[]>("/tasks"),
  policies: () => request<PolicyOut[]>("/policies"),

  scenarioSuites: (limit = 100, offset = 0) =>
    request<SuiteSummaryOut[]>(`/scenario-suites${qs({ limit, offset })}`),
  scenarioSuite: (name: string, version: string) =>
    request<SuiteDetailOut>(
      `/scenario-suites/${encodeURIComponent(name)}/${encodeURIComponent(version)}`,
    ),
  createScenarioSuite: (body: SuiteCreateIn) =>
    request<SuiteDetailOut>("/scenario-suites", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  experiments: (params: { limit?: number; offset?: number; status?: string } = {}) =>
    request<ExperimentSummaryOut[]>(`/experiments${qs(params)}`),
  experiment: (id: string) => request<ExperimentDetailOut>(`/experiments/${id}`),
  createExperiment: (body: ExperimentCreateIn) =>
    request<ExperimentDetailOut>("/experiments", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  startExperiment: (id: string) =>
    request<ExperimentDetailOut>(`/experiments/${id}/start`, { method: "POST" }),
  cancelExperiment: (id: string) =>
    request<ExperimentDetailOut>(`/experiments/${id}/cancel`, { method: "POST" }),
  reproduceExperiment: (id: string) =>
    request<{ source_experiment_id: string; experiment: ExperimentDetailOut }>(
      `/experiments/${id}/reproduce`,
      { method: "POST" },
    ),

  experimentEpisodes: (
    id: string,
    params: { limit?: number; offset?: number; outcome?: string; success?: boolean } = {},
  ) => request<EpisodeOut[]>(`/experiments/${id}/episodes${qs(params)}`),
  experimentMetrics: (id: string) => request<MetricSet>(`/experiments/${id}/metrics`),

  compare: (a: string, b: string) => request<CompareOut>(`/experiments/compare${qs({ a, b })}`),

  episode: (id: string) => request<EpisodeOut>(`/episodes/${id}`),
  episodeArtifacts: (id: string) =>
    request<EpisodeArtifactsOut>(`/episodes/${id}/artifacts`),
};
