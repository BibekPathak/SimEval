import { NavLink, Outlet } from "react-router-dom";
import { useAsync } from "@/hooks/useAsync";
import { api } from "@/api/client";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/tasks", label: "Tasks & Suites" },
  { to: "/new", label: "New Evaluation" },
  { to: "/experiments", label: "Experiments" },
  { to: "/compare", label: "Compare" },
];

export function Layout() {
  const health = useAsync(() => api.health(), []);

  return (
    <div className="flex min-h-full">
      <aside className="w-56 shrink-0 border-r border-border bg-panel/60">
        <div className="px-4 py-5">
          <div className="text-lg font-semibold tracking-tight">SimEval</div>
          <div className="text-xs text-muted">Robot Learning Evaluation</div>
        </div>
        <nav className="px-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `block rounded px-3 py-2 text-sm ${
                  isActive
                    ? "bg-accent/15 text-accent"
                    : "text-zinc-300 hover:bg-white/5 hover:text-zinc-100"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-6 border-t border-border px-4 py-3 text-xs">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                health.data?.status === "ok" ? "bg-emerald-400" : "bg-red-400"
              }`}
            />
            <span className="text-muted">
              API {health.loading ? "…" : health.data?.status ?? "unreachable"}
            </span>
          </div>
          {health.data && (
            <div className="mt-1 text-muted">
              worker {health.data.worker.running ? "up" : "down"} · queue{" "}
              {health.data.worker.queue_depth}
            </div>
          )}
          <div className="mt-1 text-muted">v{health.data?.version ?? "—"}</div>
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
