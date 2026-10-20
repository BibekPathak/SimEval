import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
import { usePolling } from "@/hooks/useAsync";
import { KeyValue, Panel, StatCard } from "@/components/Panel";
import { StatusBadge } from "@/components/Badge";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { integer, ms, num, pct, shortHash } from "@/lib/format";
import type {
  DataTableSort,
  EpisodeOut,
  ExperimentDetailOut,
  MetricSet,
} from "@/types";

const TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED"]);

export function ExperimentDetailPage() {
  const { id = "" } = useParams();
  const exp = usePolling(
    () => api.experiment(id),
    (e) => TERMINAL.has(e.status),
    2000,
    [id],
  );

  if (exp.loading && !exp.data) return <Loading label="Loading experiment…" />;
  if (exp.error && !exp.data) return <ErrorState message={exp.error} onRetry={exp.reload} />;
  if (!exp.data) return <EmptyState title="Experiment not found" />;

  return <Detail experiment={exp.data} reload={exp.reload} />;
}

function Detail({
  experiment,
  reload,
}: {
  experiment: ExperimentDetailOut;
  reload: () => void;
}) {
  const [actionError, setActionError] = useState<string | null>(null);
  const metrics = usePolling(
    () => api.experimentMetrics(experiment.experiment_id),
    () => TERMINAL.has(experiment.status),
    3000,
    [experiment.experiment_id, experiment.status],
  );

  const run = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
      reload();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e));
    }
  };

  const m = (metrics.data ?? experiment.metrics) as MetricSet;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{experiment.name}</h1>
            <StatusBadge status={experiment.status} />
          </div>
          <div className="mt-1 font-mono text-xs text-muted">{experiment.experiment_id}</div>
          {experiment.description && (
            <p className="mt-2 max-w-2xl text-sm text-zinc-400">{experiment.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          {!TERMINAL.has(experiment.status) && experiment.status !== "RUNNING" && (
            <button
              onClick={() => run(() => api.startExperiment(experiment.experiment_id))}
              className="rounded border border-emerald-500/40 px-3 py-1.5 text-xs text-emerald-300 hover:bg-emerald-500/10"
            >
              Start
            </button>
          )}
          {!TERMINAL.has(experiment.status) && (
            <button
              onClick={() => run(() => api.cancelExperiment(experiment.experiment_id))}
              className="rounded border border-red-500/40 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10"
            >
              Cancel
            </button>
          )}
          <button
            onClick={() => run(() => api.reproduceExperiment(experiment.experiment_id))}
            className="rounded border border-border px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5"
          >
            Reproduce
          </button>
        </div>
      </div>

      {actionError && <ErrorState message={actionError} />}
      {experiment.error && (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-200">
          <div className="font-medium">Run note</div>
          <pre className="mt-1 whitespace-pre-wrap font-mono text-xs">{experiment.error}</pre>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Success" value={`${m.n_success ?? 0}/${m.n_episodes_evaluated ?? 0}`} sub={/* rate */ pct(m.success_rate ?? null)} />
        <StatCard label="Failure rate" value={pct(m.failure_rate ?? null)} />
        <StatCard label="Infra failures" value={integer(m.n_infrastructure_failures ?? 0)} sub="excluded from rates" />
        <StatCard label="Throughput" value={m.throughput_eps_per_s != null ? `${num(m.throughput_eps_per_s, 2)}/s` : "—"} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Outcome distribution">
          {m.failure_categories && Object.keys(m.failure_categories).length > 0 ? (
            <FailureChart categories={m.failure_categories} successes={m.n_success} failures={(m.n_episodes_evaluated ?? 0) - (m.n_success ?? 0)} />
          ) : (
            <FailureChart categories={{}} successes={m.n_success ?? 0} failures={0} />
          )}
        </Panel>

        <Panel title="Evaluation configuration">
          <KeyValue
            items={[
              ["Policy", `${experiment.policy_name} ${experiment.policy_version}`],
              ["Task", `${experiment.task_name} ${experiment.task_version}`],
              ["Suite", `${experiment.suite_name} ${experiment.suite_version}`],
              ["Suite hash", <span className="font-mono text-xs">{shortHash(experiment.suite_hash, 12)}</span>],
              ["Split", experiment.split],
              ["Capture every", String(experiment.eval_config.capture_every ?? 1)],
              ["Persist artifacts", String(experiment.eval_config.persist_artifacts ?? true)],
              ["Code revision", experiment.code_revision ?? "—"],
            ]}
          />
        </Panel>
      </div>

      <Panel title="Aggregate metrics">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Metric label="Completion time (mean)" value={m.completion_time_mean_s != null ? `${num(m.completion_time_mean_s, 4)} s` : "—"} sub="successes only" />
          <Metric label="Episode length (mean)" value={m.episode_length_mean_steps != null ? `${num(m.episode_length_mean_steps, 1)} steps` : "—"} />
          <Metric label="Collision rate" value={pct(m.collision_rate ?? null)} />
          <Metric label="Return (mean / median)" value={`${num(m.return_mean, 3)} / ${num(m.return_median, 3)}`} />
          <Metric label="Wall clock (mean)" value={m.mean_wall_clock_s != null ? `${num(m.mean_wall_clock_s, 3)} s` : "—"} />
          <Metric label="Policy inference (mean)" value={ms(m.mean_policy_inference_ms ?? null)} />
        </div>
      </Panel>

      <EpisodeTable experimentId={experiment.experiment_id} terminal={TERMINAL.has(experiment.status)} />
    </div>
  );
}

function FailureChart({
  categories,
  successes,
  failures,
}: {
  categories: Record<string, number>;
  successes: number;
  failures: number;
}) {
  const data = [
    { name: "SUCCESS", count: successes, color: "#34d399" },
    ...Object.entries(categories).map(([k, v]) => ({ name: k, count: v, color: "#f87171" })),
  ];
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 40, right: 12 }}>
          <CartesianGrid stroke="#242a36" horizontal={false} />
          <XAxis type="number" tick={{ fill: "#8a94a6", fontSize: 10 }} allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fill: "#8a94a6", fontSize: 10 }} width={110} />
          <Tooltip contentStyle={{ background: "#161a22", border: "1px solid #242a36", fontSize: 12 }} />
          <Bar dataKey="count" radius={[0, 2, 2, 0]}>
            {data.map((d) => (
              <Cell key={d.name} fill={d.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {failures > 0 && (
        <div className="mt-1 text-xs text-muted">{failures} failing episode(s) across {Object.keys(categories).length} categor(ies)</div>
      )}
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="font-mono text-lg text-zinc-100">{value}</div>
      {sub && <div className="text-xs text-muted">{sub}</div>}
    </div>
  );
}

type SortKey = keyof Pick<
  EpisodeOut,
  "scenario_id" | "outcome" | "steps" | "final_ee_target_dist_m" | "wall_clock_s" | "difficulty"
>;

function EpisodeTable({ experimentId, terminal }: { experimentId: string; terminal: boolean }) {
  const [outcome, setOutcome] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [sort, setSort] = useState<DataTableSort<SortKey>>({ key: "scenario_id", dir: "asc" });

  const episodes = usePolling(
    () => api.experimentEpisodes(experimentId, { limit: 500 }),
    () => terminal,
    4000,
    [experimentId, terminal],
  );

  const rows = useMemo(() => {
    let data = episodes.data ?? [];
    if (outcome) data = data.filter((e) => e.outcome === outcome);
    if (difficulty) data = data.filter((e) => e.difficulty === difficulty);
    const sorted = [...data].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [episodes.data, outcome, difficulty, sort]);

  const outcomes = useMemo(
    () => Array.from(new Set((episodes.data ?? []).map((e) => e.outcome))).sort(),
    [episodes.data],
  );
  const difficulties = useMemo(
    () => Array.from(new Set((episodes.data ?? []).map((e) => e.difficulty))).sort(),
    [episodes.data],
  );

  const toggleSort = (key: SortKey) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));

  const Arrow = ({ k }: { k: SortKey }) =>
    sort.key === k ? <span>{sort.dir === "asc" ? " ↑" : " ↓"}</span> : null;

  return (
    <Panel
      title={`Episodes (${rows.length})`}
      action={
        <div className="flex gap-2">
          <select
            value={outcome}
            onChange={(e) => setOutcome(e.target.value)}
            className="rounded border border-border bg-bg px-2 py-1 text-xs"
          >
            <option value="">all outcomes</option>
            {outcomes.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
          <select
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className="rounded border border-border bg-bg px-2 py-1 text-xs"
          >
            <option value="">all difficulties</option>
            {difficulties.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
      }
    >
      {episodes.loading && !episodes.data && <Loading />}
      {episodes.error && !episodes.data && <ErrorState message={episodes.error} onRetry={episodes.reload} />}
      {rows.length === 0 && !episodes.loading ? (
        <EmptyState title="No episodes yet" hint={terminal ? "This run produced no episodes." : "Episodes appear as the run progresses."} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="cursor-pointer py-2" onClick={() => toggleSort("scenario_id")}>
                  Scenario<Arrow k="scenario_id" />
                </th>
                <th className="py-2">Difficulty</th>
                <th className="cursor-pointer py-2" onClick={() => toggleSort("outcome")}>
                  Outcome<Arrow k="outcome" />
                </th>
                <th className="cursor-pointer py-2" onClick={() => toggleSort("steps")}>
                  Steps<Arrow k="steps" />
                </th>
                <th className="cursor-pointer py-2" onClick={() => toggleSort("final_ee_target_dist_m")}>
                  Final dist<Arrow k="final_ee_target_dist_m" />
                </th>
                <th className="py-2">Collisions</th>
                <th className="cursor-pointer py-2" onClick={() => toggleSort("wall_clock_s")}>
                  Wall<Arrow k="wall_clock_s" />
                </th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((ep) => (
                <tr key={ep.episode_id} className="border-t border-border/60">
                  <td className="py-2 font-mono text-xs text-zinc-300">{ep.scenario_id}</td>
                  <td className="py-2 text-zinc-400">{ep.difficulty}</td>
                  <td className="py-2">
                    <span className={ep.success ? "text-emerald-300" : "text-red-300"}>{ep.outcome}</span>
                  </td>
                  <td className="py-2 font-mono text-zinc-300">{ep.steps}</td>
                  <td className="py-2 font-mono text-zinc-300">{num(ep.final_ee_target_dist_m, 4)}</td>
                  <td className="py-2 font-mono text-zinc-300">{ep.collision_steps}</td>
                  <td className="py-2 font-mono text-zinc-300">{num(ep.wall_clock_s, 3)}s</td>
                  <td className="py-2 text-right">
                    <Link to={`/episodes/${ep.episode_id}`} className="text-xs text-accent hover:underline">
                      Inspect
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
