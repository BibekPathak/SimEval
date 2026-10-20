import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { Panel } from "@/components/Panel";
import { EmptyState, ErrorState, Loading } from "@/components/States";
import { shortHash } from "@/lib/format";
import type { ExperimentCreateIn } from "@/types";

const SPLITS = ["all", "dev", "validation", "held_out"];

export function NewEvaluationPage() {
  const navigate = useNavigate();
  const tasks = useAsync(() => api.tasks(), []);
  const policies = useAsync(() => api.policies(), []);
  const suites = useAsync(() => api.scenarioSuites(), []);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [taskKey, setTaskKey] = useState("");
  const [policyName, setPolicyName] = useState("");
  const [suiteKey, setSuiteKey] = useState("");
  const [split, setSplit] = useState("all");
  const [captureEvery, setCaptureEvery] = useState(1);
  const [persistArtifacts, setPersistArtifacts] = useState(true);
  const [timeoutS, setTimeoutS] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [autoStart, setAutoStart] = useState(true);

  // Defaults once data loads.
  useMemo(() => {
    if (!taskKey && tasks.data?.length) setTaskKey(`${tasks.data[0].name}|${tasks.data[0].version}`);
    if (!policyName && policies.data?.length) setPolicyName(policies.data[0].name);
    if (!suiteKey && suites.data?.length)
      setSuiteKey(`${suites.data[0].suite_name}|${suites.data[0].suite_version}`);
  }, [tasks.data, policies.data, suites.data, taskKey, policyName, suiteKey]);

  const selectedSuite = suites.data?.find(
    (s) => `${s.suite_name}|${s.suite_version}` === suiteKey,
  );

  const errors = validate({ name, taskKey, policyName, suiteKey, captureEvery, timeoutS });

  const submit = async () => {
    setSubmitError(null);
    if (Object.keys(errors).length > 0) return;
    const [taskName, taskVersion] = taskKey.split("|");
    const [suiteName, suiteVersion] = suiteKey.split("|");
    const body: ExperimentCreateIn = {
      name: name.trim(),
      description: description.trim() || null,
      policy_name: policyName,
      task_name: taskName,
      task_version: taskVersion,
      suite_name: suiteName,
      suite_version: suiteVersion,
      split,
      capture_every: Number(captureEvery),
      persist_artifacts: persistArtifacts,
      timeout_s: timeoutS === "" ? null : Number(timeoutS),
    };
    setSubmitting(true);
    try {
      const created = await api.createExperiment(body);
      if (autoStart) await api.startExperiment(created.experiment_id);
      navigate(`/experiments/${created.experiment_id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const loading = tasks.loading || policies.loading || suites.loading;
  const error = tasks.error || policies.error || suites.error;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">New Evaluation</h1>

      {error && <ErrorState message={error} />}
      {loading && <Loading />}

      {!loading && !error && (suites.data?.length ?? 0) === 0 && (
        <EmptyState
          title="No scenario suites available"
          hint="Create a scenario suite before starting an evaluation."
          action={<CreateSuiteForm onCreated={(name) => setSuiteKey(name)} />}
        />
      )}

      {!loading && !error && (suites.data?.length ?? 0) > 0 && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-4">
            <Panel title="Configuration">
              <div className="space-y-4">
                <Field label="Name" error={errors.name}>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="baseline reach sweep"
                    className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                  />
                </Field>

                <Field label="Description">
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={2}
                    className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                  />
                </Field>

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field label="Task" error={errors.taskKey}>
                    <select
                      value={taskKey}
                      onChange={(e) => setTaskKey(e.target.value)}
                      className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    >
                      {tasks.data?.map((t) => (
                        <option key={`${t.name}-${t.version}`} value={`${t.name}|${t.version}`}>
                          {t.name} {t.version}
                        </option>
                      ))}
                    </select>
                  </Field>

                  <Field label="Policy" error={errors.policyName}>
                    <select
                      value={policyName}
                      onChange={(e) => setPolicyName(e.target.value)}
                      className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    >
                      {policies.data?.map((p) => (
                        <option key={p.name} value={p.name}>
                          {p.name} {p.version}
                        </option>
                      ))}
                    </select>
                  </Field>

                  <Field label="Scenario suite" error={errors.suiteKey}>
                    <select
                      value={suiteKey}
                      onChange={(e) => setSuiteKey(e.target.value)}
                      className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    >
                      {suites.data?.map((s) => (
                        <option key={`${s.suite_name}-${s.suite_version}`} value={`${s.suite_name}|${s.suite_version}`}>
                          {s.suite_name} {s.suite_version} ({s.n_scenarios})
                        </option>
                      ))}
                    </select>
                  </Field>

                  <Field label="Split">
                    <select
                      value={split}
                      onChange={(e) => setSplit(e.target.value)}
                      className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    >
                      {SPLITS.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </Field>

                  <Field label="Capture every N steps" error={errors.captureEvery}>
                    <input
                      type="number"
                      min={1}
                      value={captureEvery}
                      onChange={(e) => setCaptureEvery(Number(e.target.value))}
                      className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    />
                  </Field>

                  <Field label="Timeout (seconds, optional)" error={errors.timeoutS}>
                    <input
                      type="number"
                      min={0}
                      value={timeoutS}
                      onChange={(e) => setTimeoutS(e.target.value)}
                      placeholder="default"
                      className="w-full rounded border border-border bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
                    />
                  </Field>
                </div>

                <label className="flex items-center gap-2 text-sm text-zinc-300">
                  <input
                    type="checkbox"
                    checked={persistArtifacts}
                    onChange={(e) => setPersistArtifacts(e.target.checked)}
                  />
                  Persist episode artifacts
                </label>
                <label className="flex items-center gap-2 text-sm text-zinc-300">
                  <input
                    type="checkbox"
                    checked={autoStart}
                    onChange={(e) => setAutoStart(e.target.checked)}
                  />
                  Start immediately after creation
                </label>
              </div>
            </Panel>
          </div>

          <div className="space-y-4">
            <Panel title="Review">
              <ul className="space-y-2 text-sm">
                <Review label="Task" value={taskKey.replace("|", " ") || "—"} />
                <Review label="Policy" value={policyName || "—"} />
                <Review
                  label="Suite"
                  value={
                    selectedSuite
                      ? `${selectedSuite.suite_name} ${selectedSuite.suite_version}`
                      : "—"
                  }
                />
                <Review
                  label="Suite hash"
                  value={selectedSuite ? shortHash(selectedSuite.content_hash, 12) : "—"}
                />
                <Review
                  label="Scenarios in split"
                  value={
                    selectedSuite
                      ? String(
                          split === "all"
                            ? selectedSuite.n_scenarios
                            : selectedSuite.counts[split] ?? 0,
                        )
                      : "—"
                  }
                />
                <Review label="Split" value={split} />
                <Review label="Capture every" value={`${captureEvery} step(s)`} />
              </ul>

              {submitError && (
                <div className="mt-3 rounded border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-300">
                  {submitError}
                </div>
              )}

              <button
                disabled={submitting || Object.keys(errors).length > 0}
                onClick={submit}
                className="mt-4 w-full rounded bg-accent/90 px-3 py-2 text-sm font-medium text-white hover:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                {submitting ? "Submitting…" : autoStart ? "Create & start evaluation" : "Create evaluation"}
              </button>
              {Object.keys(errors).length > 0 && (
                <div className="mt-2 text-xs text-red-300">Resolve the highlighted fields.</div>
              )}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

function validate(fields: {
  name: string;
  taskKey: string;
  policyName: string;
  suiteKey: string;
  captureEvery: number;
  timeoutS: string;
}): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!fields.name.trim()) errors.name = "Name is required";
  else if (fields.name.length > 160) errors.name = "Name is too long (max 160)";
  if (!fields.taskKey) errors.taskKey = "Select a task";
  if (!fields.policyName) errors.policyName = "Select a policy";
  if (!fields.suiteKey) errors.suiteKey = "Select a scenario suite";
  if (!Number.isInteger(fields.captureEvery) || fields.captureEvery < 1)
    errors.captureEvery = "Must be a positive integer";
  if (fields.timeoutS !== "") {
    const n = Number(fields.timeoutS);
    if (Number.isNaN(n) || n < 0) errors.timeoutS = "Must be a non-negative number";
  }
  return errors;
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-muted">{label}</span>
      {children}
      {error && <span className="mt-1 block text-xs text-red-300">{error}</span>}
    </label>
  );
}

function Review({ label, value }: { label: string; value: string }) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-border/50 pb-1">
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <span className="font-mono text-xs text-zinc-200">{value}</span>
    </li>
  );
}

function CreateSuiteForm({ onCreated }: { onCreated: (key: string) => void }) {
  const [suiteName, setSuiteName] = useState("reach-default");
  const [n, setN] = useState(30);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const create = async () => {
    setBusy(true);
    setErr(null);
    try {
      const created = await api.createScenarioSuite({
        suite_name: suiteName,
        suite_version: "v1",
        n_scenarios: n,
      });
      onCreated(`${created.suite_name}|${created.suite_version}`);
      window.location.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-sm space-y-3 text-left">
      <input
        value={suiteName}
        onChange={(e) => setSuiteName(e.target.value)}
        className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
        placeholder="suite name"
      />
      <input
        type="number"
        value={n}
        min={1}
        onChange={(e) => setN(Number(e.target.value))}
        className="w-full rounded border border-border bg-bg px-3 py-2 text-sm"
      />
      <button
        onClick={create}
        disabled={busy || !suiteName.trim()}
        className="w-full rounded bg-accent/90 px-3 py-2 text-sm font-medium text-white hover:bg-accent disabled:opacity-40"
      >
        {busy ? "Creating…" : "Create suite"}
      </button>
      {err && <div className="text-xs text-red-300">{err}</div>}
    </div>
  );
}
