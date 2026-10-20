import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { Panel } from "@/components/Panel";
import { StatusBadge } from "@/components/Badge";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { pct, relTime, shortHash } from "@/lib/format";
import type { MetricSet } from "@/types";

const FILTERS = ["ALL", "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"];

export function ExperimentsPage() {
  const [status, setStatus] = useState("ALL");
  const list = useAsync(
    () => api.experiments({ limit: 100, status: status === "ALL" ? undefined : status }),
    [status],
  );

  const rate = (metrics: Record<string, unknown>): number | null => {
    const m = metrics as Partial<MetricSet>;
    return typeof m.success_rate === "number" ? m.success_rate : null;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Experiments</h1>
        <Link
          to="/new"
          className="rounded bg-accent/90 px-3 py-1.5 text-sm font-medium text-white hover:bg-accent"
        >
          New evaluation
        </Link>
      </div>

      <div className="flex gap-2">
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setStatus(f)}
            className={`rounded border px-3 py-1 text-xs ${
              status === f
                ? "border-accent/50 bg-accent/15 text-accent"
                : "border-border text-zinc-300 hover:bg-white/5"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      <Panel>
        {list.loading && <Loading />}
        {list.error && <ErrorState message={list.error} onRetry={list.reload} />}
        {!list.loading && !list.error && (list.data?.length ?? 0) === 0 && (
          <EmptyState title="No experiments match this filter" />
        )}
        {!list.loading && !list.error && list.data && list.data.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2">Name</th>
                <th className="py-2">Policy</th>
                <th className="py-2">Task</th>
                <th className="py-2">Suite</th>
                <th className="py-2">Split</th>
                <th className="py-2">Status</th>
                <th className="py-2">Success</th>
                <th className="py-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {list.data.map((e) => (
                <tr key={e.experiment_id} className="border-t border-border/60 hover:bg-white/5">
                  <td className="py-2">
                    <Link to={`/experiments/${e.experiment_id}`} className="text-zinc-200 hover:text-accent">
                      {e.name}
                    </Link>
                    <div className="font-mono text-[10px] text-muted">{e.experiment_id}</div>
                  </td>
                  <td className="py-2 text-zinc-400">{e.policy_name}</td>
                  <td className="py-2 text-zinc-400">
                    {e.task_name} {e.task_version}
                  </td>
                  <td className="py-2 font-mono text-xs text-zinc-400">{shortHash(e.suite_hash)}</td>
                  <td className="py-2 text-zinc-400">{e.split}</td>
                  <td className="py-2">
                    <StatusBadge status={e.status} />
                  </td>
                  <td className="py-2 font-mono text-zinc-300">{pct(rate(e.metrics))}</td>
                  <td className="py-2 text-xs text-muted">{relTime(e.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
