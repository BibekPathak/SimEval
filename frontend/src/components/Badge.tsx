import type { ReactNode } from "react";
import { STATUS_COLORS, VERDICT_COLORS } from "@/lib/format";

export function Badge({
  children,
  tone = "zinc",
}: {
  children: ReactNode;
  tone?: "zinc" | "green" | "red" | "amber" | "sky" | "fuchsia";
}) {
  const tones: Record<string, string> = {
    zinc: "text-zinc-300 bg-zinc-500/10 border-zinc-500/30",
    green: "text-emerald-300 bg-emerald-500/10 border-emerald-500/30",
    red: "text-red-300 bg-red-500/10 border-red-500/30",
    amber: "text-amber-300 bg-amber-500/10 border-amber-500/30",
    sky: "text-sky-300 bg-sky-500/10 border-sky-500/30",
    fuchsia: "text-fuchsia-300 bg-fuchsia-500/10 border-fuchsia-500/30",
  };
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? "text-zinc-300 bg-zinc-500/10 border-zinc-500/30";
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

export function VerdictBadge({ verdict }: { verdict: string }) {
  const cls = VERDICT_COLORS[verdict] ?? "text-zinc-400 bg-zinc-500/10 border-zinc-500/30";
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${cls}`}>
      {verdict}
    </span>
  );
}
