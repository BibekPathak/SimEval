// Formatting helpers shared across pages.

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function integer(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString();
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)} ms`;
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const diff = Date.now() - then;
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

export function shortHash(hash: string | null | undefined, len = 10): string {
  if (!hash) return "—";
  return hash.slice(0, len);
}

export const STATUS_COLORS: Record<string, string> = {
  QUEUED: "text-amber-300 bg-amber-500/10 border-amber-500/30",
  RUNNING: "text-sky-300 bg-sky-500/10 border-sky-500/30",
  COMPLETED: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
  FAILED: "text-red-300 bg-red-500/10 border-red-500/30",
  CANCELLED: "text-zinc-300 bg-zinc-500/10 border-zinc-500/30",
};

export const VERDICT_COLORS: Record<string, string> = {
  IMPROVED: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
  REGRESSED: "text-red-300 bg-red-500/10 border-red-500/30",
  INCONCLUSIVE: "text-amber-300 bg-amber-500/10 border-amber-500/30",
  MISSING: "text-zinc-400 bg-zinc-500/10 border-zinc-500/30",
};

export const OUTCOME_COLORS: Record<string, string> = {
  SUCCESS: "text-emerald-300",
  TIMEOUT: "text-amber-300",
  TARGET_NOT_REACHED: "text-orange-300",
  COLLISION: "text-red-300",
  INVALID_ACTION: "text-fuchsia-300",
  NUMERICAL_FAILURE: "text-fuchsia-300",
  SIMULATOR_ERROR: "text-rose-300",
  OTHER_FAILURE: "text-zinc-300",
};

// Badge tone per outcome, for <Badge tone={...}>.
export const OUTCOME_TONE: Record<string, "zinc" | "green" | "red" | "amber" | "sky" | "fuchsia"> = {
  SUCCESS: "green",
  TIMEOUT: "amber",
  TARGET_NOT_REACHED: "amber",
  COLLISION: "red",
  INVALID_ACTION: "fuchsia",
  NUMERICAL_FAILURE: "fuchsia",
  SIMULATOR_ERROR: "red",
  OTHER_FAILURE: "zinc",
};
