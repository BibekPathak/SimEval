import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { KeyValue, Panel, StatCard } from "@/components/Panel";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { integer, ms, num, OUTCOME_TONE } from "@/lib/format";
import { Badge } from "@/components/Badge";

export function EpisodePage() {
  const { id = "" } = useParams();
  const episode = useAsync(() => api.episode(id), [id]);
  const artifacts = useAsync(() => api.episodeArtifacts(id), [id]);

  if (episode.loading) return <Loading label="Loading episode…" />;
  if (episode.error) return <ErrorState message={episode.error} onRetry={episode.reload} />;
  if (!episode.data) return <EmptyState title="Episode not found" />;

  const ep = episode.data;
  const tone = OUTCOME_TONE[ep.outcome] ?? "zinc";

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">Episode inspection</h1>
          <Badge tone={tone}>{ep.outcome}</Badge>
        </div>
        <div className="mt-1 font-mono text-xs text-muted">{ep.episode_id}</div>
        <Link to={`/experiments/${ep.experiment_id}`} className="text-xs text-accent hover:underline">
          ← back to experiment
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Steps" value={integer(ep.steps)} sub={`${num(ep.sim_time_s, 2)} s sim`} />
        <StatCard label="Final EE-target dist" value={`${num(ep.final_ee_target_dist_m, 4)} m`} sub={`min ${num(ep.min_ee_target_dist_m, 4)} m`} />
        <StatCard label="Collision steps" value={integer(ep.collision_steps)} sub={`max ${ep.max_collision_count} contacts`} />
        <StatCard label="Return" value={num(ep.return_sum, 3)} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Outcome and evidence">
          <div className="mb-3 rounded border border-border bg-bg/40 px-3 py-2 text-sm text-zinc-200">
            {ep.explanation}
          </div>
          <KeyValue
            items={[
              ["Success", ep.success ? "yes" : "no"],
              ["Failure category", ep.failure_category ?? "—"],
              ["Deciding rule", <span className="font-mono text-xs">{ep.rule}</span>],
              ["Scenario", ep.scenario_id],
              ["Split / difficulty", `${ep.split} / ${ep.difficulty}`],
              ["Seed", String(ep.seed)],
            ]}
          />
          {ep.error && (
            <pre className="mt-3 max-h-40 overflow-auto rounded border border-red-500/30 bg-red-500/5 p-2 font-mono text-xs text-red-200">
              {ep.error}
            </pre>
          )}
        </Panel>

        <Panel title="Recorded metrics">
          <KeyValue
            items={[
              ["Policy", `${ep.policy_name} ${ep.policy_version}`],
              ["Task", `${ep.task_name} ${ep.task_version}`],
              ["Initial dist", `${num(ep.initial_ee_target_dist_m, 4)} m`],
              ["Wall clock", `${num(ep.wall_clock_s, 4)} s`],
              ["Policy inference", ms(ep.policy_inference_s * 1000)],
              ["Real-time factor", num((ep.metrics.real_time_factor as number) ?? null, 2)],
            ]}
          />
        </Panel>
      </div>

      <Panel title="Episode artifacts">
        {artifacts.loading && <Loading />}
        {artifacts.error && <ErrorState message={artifacts.error} onRetry={artifacts.reload} />}
        {artifacts.data && !artifacts.data.exists && (
          <EmptyState
            title="No artifacts persisted for this episode"
            hint="Artifact persistence may have been disabled for this run."
          />
        )}
        {artifacts.data && artifacts.data.exists && (
          <div>
            <div className="font-mono text-xs text-muted">{artifacts.data.artifact_ref}</div>
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <th className="py-2">Array</th>
                  <th className="py-2">Shape</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(artifacts.data.arrays).map(([k, shape]) => (
                  <tr key={k} className="border-t border-border/60">
                    <td className="py-1.5 font-mono text-zinc-200">{k}</td>
                    <td className="py-1.5 font-mono text-zinc-400">[{shape.join(", ")}]</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-3 text-xs text-muted">
              These compressed per-step arrays (<span className="font-mono">.npz</span>) are persisted
              and referenced by this episode. Per-step time-series plotting requires an array-content
              endpoint, which is not yet exposed; only shapes are shown to avoid displaying
              reconstructed or invented data.
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}
