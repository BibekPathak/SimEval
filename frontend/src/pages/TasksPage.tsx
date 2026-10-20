import { useState } from "react";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { KeyValue, Panel } from "@/components/Panel";
import { Badge } from "@/components/Badge";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { integer, num, shortHash } from "@/lib/format";
import type { SuiteDetailOut } from "@/types";

export function TasksPage() {
  const tasks = useAsync(() => api.tasks(), []);
  const suites = useAsync(() => api.scenarioSuites(), []);
  const [selected, setSelected] = useState<SuiteDetailOut | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const openSuite = async (name: string, version: string) => {
    setDetailError(null);
    try {
      setSelected(await api.scenarioSuite(name, version));
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Tasks & Scenario Suites</h1>

      <Panel title="Tasks">
        {tasks.loading && <Loading />}
        {tasks.error && <ErrorState message={tasks.error} onRetry={tasks.reload} />}
        {!tasks.loading && !tasks.error && (tasks.data?.length ?? 0) === 0 && (
          <EmptyState title="No tasks registered" hint="The backend syncs tasks on startup." />
        )}
        {!tasks.loading && !tasks.error && tasks.data && tasks.data.length > 0 && (
          <div className="space-y-4">
            {tasks.data.map((t) => (
              <div key={`${t.name}-${t.version}`} className="rounded border border-border p-3">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-zinc-100">{t.name}</span>
                  <Badge tone="sky">{t.version}</Badge>
                </div>
                {t.description && <p className="mt-1 text-sm text-muted">{t.description}</p>}
                <div className="mt-3">
                  <KeyValue
                    items={Object.entries(t.spec).map(([k, v]) => [
                      k,
                      typeof v === "number" ? num(v) : String(v),
                    ])}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Scenario suites">
        {suites.loading && <Loading />}
        {suites.error && <ErrorState message={suites.error} onRetry={suites.reload} />}
        {!suites.loading && !suites.error && (suites.data?.length ?? 0) === 0 && (
          <EmptyState
            title="No scenario suites yet"
            hint="Create one from the New Evaluation page or via the API."
          />
        )}
        {!suites.loading && !suites.error && suites.data && suites.data.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="py-2">Suite</th>
                <th className="py-2">Task</th>
                <th className="py-2">Scenarios</th>
                <th className="py-2">Splits</th>
                <th className="py-2">Hash</th>
                <th className="py-2"></th>
              </tr>
            </thead>
            <tbody>
              {suites.data.map((s) => (
                <tr key={`${s.suite_name}-${s.suite_version}`} className="border-t border-border/60">
                  <td className="py-2">
                    <span className="text-zinc-200">{s.suite_name}</span>{" "}
                    <span className="text-muted">{s.suite_version}</span>
                  </td>
                  <td className="py-2 text-zinc-400">
                    {s.task_name} {s.task_version}
                  </td>
                  <td className="py-2 font-mono text-zinc-300">{integer(s.n_scenarios)}</td>
                  <td className="py-2 text-xs text-zinc-400">
                    {Object.entries(s.counts)
                      .map(([k, v]) => `${k}:${v}`)
                      .join("  ")}
                  </td>
                  <td className="py-2 font-mono text-xs text-zinc-400">{shortHash(s.content_hash)}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => openSuite(s.suite_name, s.suite_version)}
                      className="rounded border border-border px-2 py-1 text-xs text-zinc-300 hover:bg-white/5"
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {detailError && <div className="mt-3"><ErrorState message={detailError} /></div>}
      </Panel>

      {selected && <SuiteInspector suite={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function SuiteInspector({ suite, onClose }: { suite: SuiteDetailOut; onClose: () => void }) {
  const scenarios = suite.payload.scenarios ?? [];
  return (
    <Panel
      title={`Suite ${suite.suite_name} ${suite.suite_version}`}
      action={
        <button
          onClick={onClose}
          className="rounded border border-border px-2 py-1 text-xs text-zinc-300 hover:bg-white/5"
        >
          Close
        </button>
      }
    >
      <KeyValue
        items={[
          ["Content hash", <span className="font-mono text-xs">{suite.content_hash}</span>],
          ["Task", `${suite.task_name} ${suite.task_version}`],
          ["Scenarios", integer(suite.n_scenarios)],
          ["Splits", Object.entries(suite.counts).map(([k, v]) => `${k}:${v}`).join(", ")],
        ]}
      />
      <div className="mt-4">
        <div className="mb-2 text-xs uppercase tracking-wide text-muted">
          Scenario configurations ({scenarios.length})
        </div>
        <div className="max-h-80 overflow-auto rounded border border-border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-panel">
              <tr className="text-left text-muted">
                <th className="px-2 py-1">ID</th>
                <th className="px-2 py-1">Seed</th>
                <th className="px-2 py-1">Split</th>
                <th className="px-2 py-1">Difficulty</th>
                <th className="px-2 py-1">Target (x,y,z)</th>
                <th className="px-2 py-1">Init posture</th>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((s) => (
                <tr key={s.scenario_id} className="border-t border-border/60">
                  <td className="px-2 py-1 font-mono">{s.scenario_id}</td>
                  <td className="px-2 py-1 font-mono">{s.seed}</td>
                  <td className="px-2 py-1">{s.split}</td>
                  <td className="px-2 py-1">{s.difficulty}</td>
                  <td className="px-2 py-1 font-mono">
                    {s.target_position.map((v) => v.toFixed(2)).join(", ")}
                  </td>
                  <td className="px-2 py-1 font-mono">
                    {s.initial_qpos ? s.initial_qpos.map((v) => v.toFixed(2)).join(", ") : "default"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  );
}
