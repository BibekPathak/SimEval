import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted">
      <span className="h-3 w-3 animate-spin rounded-full border-2 border-border border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="rounded border border-red-500/30 bg-red-500/5 px-4 py-4 text-sm">
      <div className="font-medium text-red-300">Request failed</div>
      <div className="mt-1 font-mono text-xs text-red-200/80">{message}</div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded border border-red-500/40 px-3 py-1 text-xs text-red-200 hover:bg-red-500/10"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded border border-dashed border-border px-4 py-10 text-center">
      <div className="text-sm text-zinc-300">{title}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
