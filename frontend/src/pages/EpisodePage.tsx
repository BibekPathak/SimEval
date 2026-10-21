import { useParams } from "react-router-dom";
import { Link } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
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

      <EpisodeSeries episodeId={id} />

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
              Compressed per-step arrays (<span className="font-mono">.npz</span>) persisted for this
              episode. The plots above are rendered from these recorded arrays via
              <span className="font-mono"> GET /api/v1/episodes/&#123;id&#125;/artifacts/series</span>;
              nothing is reconstructed or invented.
            </p>
          </div>
        )}
      </Panel>
    </div>
  );
}

// Real per-step plots built from the recorded artifact arrays (downsampled
// server-side). No series is synthesised: if an array is absent it is omitted.
function EpisodeSeries({ episodeId }: { episodeId: string }) {
  const series = useAsync(
    () =>
      api.episodeSeries(episodeId, [
        "source_step",
        "ee_target_dist",
        "qpos",
        "action",
        "collision",
      ]),
    [episodeId],
  );

  if (series.loading) return <Loading label="Loading recorded series…" />;
  if (series.error)
    return (
      <Panel title="Recorded time-series">
        <EmptyState title="No recorded series available" hint={series.error} />
      </Panel>
    );
  if (!series.data || !series.data.exists || series.data.n_steps === 0) {
    return (
      <Panel title="Recorded time-series">
        <EmptyState title="No recorded steps for this episode" />
      </Panel>
    );
  }

  const d = series.data;
  // Scalar-per-step arrays are stored with shape (T, 1); flatten them.
  const flat = (
    name: string,
  ): number[] | undefined => {
    const raw = d.series[name];
    if (!raw) return undefined;
    return raw.map((row) => (Array.isArray(row) ? row[0] : (row as number)));
  };
  const steps = flat("source_step") ?? [];
  const dist = flat("ee_target_dist");
  const qpos = d.series["qpos"] as number[][] | undefined;
  const action = d.series["action"] as number[][] | undefined;

  const distData = steps.map((s, i) => ({ step: s, dist: dist?.[i] ?? null }));

  const jointData = steps.map((s, i) => {
    const row: Record<string, number | null> = { step: s };
    if (qpos) qpos[i]?.forEach((v, j) => (row[`q${j + 1}`] = v));
    return row;
  });

  const actionData = steps.map((s, i) => {
    const row: Record<string, number | null> = { step: s };
    if (action) action[i]?.forEach((v, j) => (row[`a${j + 1}`] = v));
    return row;
  });

  const collisions = flat("collision") ?? [];
  const collisionSteps = steps.filter((_, i) => (collisions[i] ?? 0) > 0);

  return (
    <>
      <Panel
        title="End-effector to target distance"
        action={
          <span className="text-xs text-muted">
            {d.n_steps} steps{ d.stride > 1 ? ` · downsampled ×${d.stride}` : "" }
          </span>
        }
      >
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={distData} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
              <CartesianGrid stroke="#242a36" />
              <XAxis dataKey="step" tick={{ fill: "#8a94a6", fontSize: 10 }} />
              <YAxis tick={{ fill: "#8a94a6", fontSize: 10 }} />
              <Tooltip contentStyle={{ background: "#161a22", border: "1px solid #242a36", fontSize: 12 }} />
              <ReferenceLine y={0.05} stroke="#34d399" strokeDasharray="4 4" label={{ value: "success", fill: "#34d399", fontSize: 10 }} />
              <Line type="monotone" dataKey="dist" stroke="#5b8def" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Joint positions (recorded)">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={jointData} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
                <CartesianGrid stroke="#242a36" />
                <XAxis dataKey="step" tick={{ fill: "#8a94a6", fontSize: 10 }} />
                <YAxis tick={{ fill: "#8a94a6", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#161a22", border: "1px solid #242a36", fontSize: 12 }} />
                {[1, 2, 3, 4].map((j, idx) => (
                  <Line
                    key={j}
                    type="monotone"
                    dataKey={`q${j}`}
                    dot={false}
                    strokeWidth={1.5}
                    stroke={["#5b8def", "#f59e0b", "#34d399", "#f472b6"][idx]}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Commanded actions (recorded)">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={actionData} margin={{ top: 8, right: 12, bottom: 4, left: -12 }}>
                <CartesianGrid stroke="#242a36" />
                <XAxis dataKey="step" tick={{ fill: "#8a94a6", fontSize: 10 }} />
                <YAxis tick={{ fill: "#8a94a6", fontSize: 10 }} />
                <Tooltip contentStyle={{ background: "#161a22", border: "1px solid #242a36", fontSize: 12 }} />
                {[1, 2, 3, 4].map((j, idx) => (
                  <Line
                    key={j}
                    type="monotone"
                    dataKey={`a${j}`}
                    dot={false}
                    strokeWidth={1.5}
                    stroke={["#5b8def", "#f59e0b", "#34d399", "#f472b6"][idx]}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>

      <Panel title="Contact events">
        {collisionSteps.length === 0 ? (
          <EmptyState title="No end-effector/floor contacts recorded" />
        ) : (
          <div className="text-sm text-zinc-300">
            {collisionSteps.length} recorded step(s) with contact at steps{" "}
            <span className="font-mono text-xs">{collisionSteps.slice(0, 40).join(", ")}</span>
            {collisionSteps.length > 40 ? " …" : ""}
          </div>
        )}
      </Panel>
    </>
  );
}
