import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { Panel, StatCard } from "@/components/Panel";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { StatusBadge } from "@/components/Badge";
import { integer, pct, relTime, shortHash } from "@/lib/format";
import type { ExperimentSummaryOut, MetricSet } from "@/types";

function successRate(e: ExperimentSummaryOut): number | null {
  const m = e.metrics as Partial<MetricSet>;
  return typeof m.success_rate === "number" ? m.success_rate : null;
}

export function OverviewPage() {
  const experiments = useAsync(() => api.experiments({ limit: 50 }), []);
  const tasks = useAsync(() => api.tasks(), []);
  const suites = useAsync(() => api.scenarioSuites(), []);
  const health = useAsync(() => api.health(), []);

  const loading = experiments.loading || tasks.loading || suites.loading;
  const error = experiments.error || tasks.error || suites.error;

  const rows = experiments.data ?? [];
  const completed = rows.filter((e) => e.status === "COMPLETED");
  const running = rows.filter((e) => e.status === "RUNNING" || e.status === "QUEUED");

  const trend = [...completed]
    .reverse()
    .map((e) => ({
      name: e.name.slice(0, 14),
      rate: successRate(e) ?? 0,
      id: e.experiment_id,
    }));

  // "Regressions" here means completed experiments whose latest success rate is
  // below an earlier completed run of the same policy (a simple, honest signal;
  // rigorous regression detection lives on the Compare page).
  const regressions = detectRegressions(completed);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Overview</h1>
        <Link
          to="/new"
          className="rounded bg-accent/90 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent"
        >
          New evaluation
        </Link>
      </div>

      {error && <ErrorState message={error} onRetry={experiments.reload} />}
      {loading && <Loading />}

      {!loading && !error && (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Experiments" value={integer(rows.length)} sub={`${completed.length} completed`} />
            <StatCard
              label="Active jobs"
              value={integer(running.length)}
              sub={health.data ? `queue depth ${health.data.worker.queue_depth}` : undefined}
            />
            <StatCard label="Tasks" value={integer(tasks.data?.length ?? 0)} />
            <StatCard label="Scenario suites" value={integer(suites.data?.length ?? 0)} />
          </div>

          <Panel title="Latest policy evaluation">
            {completed.length === 0 ? (
              <EmptyState
                title="No completed experiments yet"
                hint="Run a baseline and candidate policy to populate this view."
                action={
                  <Link to="/new" className="text-accent hover:underline">
                    Create an evaluation →
                  </Link>
                }
              />
            ) : (
              <LatestEvaluation experiment={completed[0]} />
            )}
          </Panel>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Panel title="Success-rate trend (completed runs, oldest → newest)">
              {trend.length < 2 ? (
                <EmptyState title="Not enough completed runs to plot a trend" />
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={trend} margin={{ top: 8, right: 8, bottom: 8, left: -18 }}>
                      <CartesianGrid stroke="#242a36" vertical={false} />
                      <XAxis dataKey="name" tick={{ fill: "#8a94a6", fontSize: 10 }} interval={0} angle={-30} textAnchor="end" height={60} />
                      <YAxis domain={[0, 1]} tick={{ fill: "#8a94a6", fontSize: 10 }} />
                      <Tooltip
                        contentStyle={{ background: "#161a22", border: "1px solid #242a36", fontSize: 12 }}
                        formatter={(v: number) => [`${(v * 100).toFixed(1)}%`, "success"]}
                      />
                      <Bar dataKey="rate" radius={[2, 2, 0, 0]}>
                        {trend.map((t) => (
                          <Cell key={t.id} fill="#5b8def" />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </Panel>

            <Panel title="Recent regressions">
              {regressions.length === 0 ? (
                <EmptyState
                  title="No obvious regressions"
                  hint="Based on same-policy success-rate drops vs. the previous completed run."
                />
              ) : (
                <ul className="space-y-2">
                  {regressions.map((r) => (
                    <li key={r.id} className="flex items-center justify-between text-sm">
                      <Link to={`/experiments/${r.id}`} className="truncate text-zinc-200 hover:text-accent">
                        {r.name}
                      </Link>
                      <span className="font-mono text-xs text-red-300">
                        {pct(r.prev)} → {pct(r.now)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <Panel title="Recent experiments">
            {rows.length === 0 ? (
              <EmptyState title="No experiments yet" />
            ) : (
              <RecentTable rows={rows.slice(0, 8)} />
            )}
          </Panel>
        </>
      )}
    </div>
  );
}

function LatestEvaluation({ experiment }: { experiment: ExperimentSummaryOut }) {
  const m = experiment.metrics as Partial<MetricSet>;
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted">Experiment</div>
        <Link to={`/experiments/${experiment.experiment_id}`} className="text-sm text-accent hover:underline">
          {experiment.name}
        </Link>
        <div className="text-xs text-muted">{relTime(experiment.completed_at)}</div>
      </div>
      <Metric label="Success" value={`${m.n_success ?? 0}/${m.n_episodes_evaluated ?? 0}`} />
      <Metric label="Rate" value={pct(m.success_rate ?? null)} />
      <Metric label="Policy" value={`${experiment.policy_name} ${experiment.policy_version}`} />
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="font-mono text-lg text-zinc-100">{value}</div>
    </div>
  );
}

function RecentTable({ rows }: { rows: ExperimentSummaryOut[] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs uppercase tracking-wide text-muted">
          <th className="py-2">Name</th>
          <th className="py-2">Policy</th>
          <th className="py-2">Suite</th>
          <th className="py-2">Status</th>
          <th className="py-2">Success</th>
          <th className="py-2">When</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((e) => (
          <tr key={e.experiment_id} className="border-t border-border/60">
            <td className="py-2">
              <Link to={`/experiments/${e.experiment_id}`} className="text-zinc-200 hover:text-accent">
                {e.name}
              </Link>
            </td>
            <td className="py-2 text-zinc-400">{e.policy_name}</td>
            <td className="py-2 font-mono text-xs text-zinc-400">{shortHash(e.suite_hash)}</td>
            <td className="py-2">
              <StatusBadge status={e.status} />
            </td>
            <td className="py-2 font-mono text-zinc-300">{pct(successRate(e))}</td>
            <td className="py-2 text-xs text-muted">{relTime(e.created_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function detectRegressions(completed: ExperimentSummaryOut[]) {
  const byPolicy = new Map<string, ExperimentSummaryOut[]>();
  for (const e of completed) {
    const list = byPolicy.get(e.policy_name) ?? [];
    list.push(e);
    byPolicy.set(e.policy_name, list);
  }
  const out: { id: string; name: string; prev: number; now: number }[] = [];
  for (const list of byPolicy.values()) {
    const sorted = [...list].sort(
      (a, b) => new Date(a.completed_at ?? 0).getTime() - new Date(b.completed_at ?? 0).getTime(),
    );
    for (let i = 1; i < sorted.length; i++) {
      const prev = successRate(sorted[i - 1]);
      const now = successRate(sorted[i]);
      if (prev !== null && now !== null && now < prev - 1e-9) {
        out.push({ id: sorted[i].experiment_id, name: sorted[i].name, prev, now });
      }
    }
  }
  return out.slice(-5).reverse();
}
