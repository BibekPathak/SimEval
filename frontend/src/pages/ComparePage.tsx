import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { Panel } from "@/components/Panel";
import { VerdictBadge } from "@/components/Badge";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { num } from "@/lib/format";
import type { ComparisonMetric, CompareOut, ExperimentSummaryOut } from "@/types";

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const experiments = useAsync(() => api.experiments({ limit: 100 }), []);
  const [a, setA] = useState(params.get("a") ?? "");
  const [b, setB] = useState(params.get("b") ?? "");

  const comparison = useAsync(
    () => (a && b ? api.compare(a, b) : Promise.resolve(null)),
    [a, b],
  );

  const runCompare = () => setParams({ a, b });

  const eligible = (experiments.data ?? []).filter((e) => e.status === "COMPLETED");

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Policy Comparison</h1>

      <Panel title="Select two completed experiments">
        {experiments.loading && <Loading />}
        {experiments.error && <ErrorState message={experiments.error} onRetry={experiments.reload} />}
        {!experiments.loading && !experiments.error && eligible.length < 2 && (
          <EmptyState
            title="Need at least two completed experiments"
            hint="Run a baseline and a candidate policy first."
            action={<Link to="/new" className="text-accent hover:underline">New evaluation →</Link>}
          />
        )}
        {eligible.length >= 2 && (
          <div className="flex flex-wrap items-end gap-3">
            <Selector label="A (baseline)" value={a} onChange={setA} options={eligible} />
            <Selector label="B (candidate)" value={b} onChange={setB} options={eligible} />
            <button
              onClick={runCompare}
              disabled={!a || !b || a === b}
              className="rounded bg-accent/90 px-4 py-2 text-sm font-medium text-white hover:bg-accent disabled:opacity-40"
            >
              Compare
            </button>
          </div>
        )}
      </Panel>

      {comparison.loading && <Loading label="Computing comparison…" />}
      {comparison.error && <ErrorState message={comparison.error} onRetry={comparison.reload} />}
      {comparison.data && <ComparisonView data={comparison.data} />}
    </div>
  );
}

function Selector({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: ExperimentSummaryOut[];
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-muted">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-[16rem] rounded border border-border bg-bg px-3 py-2 text-sm"
      >
        <option value="">select…</option>
        {options.map((e) => (
          <option key={e.experiment_id} value={e.experiment_id}>
            {e.name} — {e.policy_name} ({e.suite_version})
          </option>
        ))}
      </select>
    </label>
  );
}

function ComparisonView({ data }: { data: CompareOut }) {
  return (
    <div className="space-y-6">
      <Panel title="Verdict">
        <div className="flex items-center gap-3">
          <span
            className={`rounded px-2 py-0.5 text-xs font-medium ${
              data.sufficient_evidence
                ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                : "border border-amber-500/30 bg-amber-500/10 text-amber-300"
            }`}
          >
            {data.sufficient_evidence ? "Sufficient evidence" : "Insufficient evidence"}
          </span>
          <span className="text-sm text-zinc-300">{data.summary}</span>
        </div>
        <div className="mt-2 text-xs text-muted">
          {data.shared_scenarios} shared scenario(s) · A: {data.n_scenarios_a} episodes · B:{" "}
          {data.n_scenarios_b} episodes
        </div>
        {!data.compatible && (
          <div className="mt-3 rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200">
            Evaluation settings differ between these experiments; any change is confounded by
            configuration.
          </div>
        )}
        {data.warnings.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-amber-200">
            {data.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Metric comparison (A → B)">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-muted">
              <th className="py-2">Metric</th>
              <th className="py-2">A</th>
              <th className="py-2">B</th>
              <th className="py-2">Δ (B−A)</th>
              <th className="py-2">95% interval</th>
              <th className="py-2">Pairs</th>
              <th className="py-2">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {data.metrics
              .filter((m) => m.metric !== "success_rate_a" && m.metric !== "success_rate_b")
              .map((m) => (
                <MetricRow key={m.metric} m={m} />
              ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="Failure-category changes (B − A)">
        {Object.keys(data.failure_category_delta).length === 0 ? (
          <EmptyState title="No failures in either run" />
        ) : (
          <div className="flex flex-wrap gap-3">
            {Object.entries(data.failure_category_delta).map(([k, v]) => (
              <div key={k} className="rounded border border-border px-3 py-2">
                <div className="text-xs uppercase tracking-wide text-muted">{k}</div>
                <div className={`font-mono text-lg ${v > 0 ? "text-red-300" : v < 0 ? "text-emerald-300" : "text-zinc-300"}`}>
                  {v > 0 ? "+" : ""}
                  {v}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Per-arm success-rate intervals">
        <CoreIntervalRow metrics={data.metrics} prefix="success_rate" />
      </Panel>
    </div>
  );
}

function MetricRow({ m }: { m: ComparisonMetric }) {
  return (
    <tr className="border-t border-border/60">
      <td className="py-2 text-zinc-200">
        {m.metric}
        <span className="ml-2 text-xs text-muted">{m.direction.replace("_", " ")}</span>
      </td>
      <td className="py-2 font-mono text-zinc-300">{num(m.a, 4)}</td>
      <td className="py-2 font-mono text-zinc-300">{num(m.b, 4)}</td>
      <td className="py-2 font-mono text-zinc-300">
        {m.delta != null ? `${m.delta > 0 ? "+" : ""}${num(m.delta, 4)}` : "—"}
      </td>
      <td className="py-2 font-mono text-xs text-zinc-400">
        {m.ci_low != null && m.ci_high != null ? `[${num(m.ci_low, 3)}, ${num(m.ci_high, 3)}]` : "—"}
      </td>
      <td className="py-2 font-mono text-zinc-400">{m.n_pairs}</td>
      <td className="py-2" title={m.reason}>
        <VerdictBadge verdict={m.verdict} />
        <div className="mt-1 max-w-xs text-[10px] text-muted">{m.reason}</div>
      </td>
    </tr>
  );
}

function CoreIntervalRow({ metrics, prefix }: { metrics: ComparisonMetric[]; prefix: string }) {
  const a = metrics.find((m) => m.metric === `${prefix}_a`);
  const b = metrics.find((m) => m.metric === `${prefix}_b`);
  if (!a || !b) return <EmptyState title="No per-arm intervals available" />;
  return (
    <div className="grid grid-cols-2 gap-4">
      <div>
        <div className="text-xs uppercase tracking-wide text-muted">A</div>
        <div className="font-mono text-sm text-zinc-200">
          {num(a.a, 3)} [{num(a.ci_low, 3)}, {num(a.ci_high, 3)}]
        </div>
        <div className="text-xs text-muted">{a.method}</div>
      </div>
      <div>
        <div className="text-xs uppercase tracking-wide text-muted">B</div>
        <div className="font-mono text-sm text-zinc-200">
          {num(b.a, 3)} [{num(b.ci_low, 3)}, {num(b.ci_high, 3)}]
        </div>
        <div className="text-xs text-muted">{b.method}</div>
      </div>
    </div>
  );
}
