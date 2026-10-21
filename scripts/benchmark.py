#!/usr/bin/env python3
"""Benchmark harness for SimEval (Milestone 7).

Measures the real execution pipeline on the current machine and writes a
reproducible report to ``docs/benchmarking.md`` (or stdout). It reports the
machine, MuJoCo version, configuration, number of episodes, and the measurement
method, so the numbers can be interpreted in context.

What is measured (all wall-clock, single process, CPU):
  * end-to-end episode throughput (episodes / second) including simulation,
    policy inference, tracing, grading, and artifact serialisation;
  * per-stage timing: policy inference and simulation vs. total;
  * artifact serialisation time and on-disk size;
  * database persistence time per episode;
  * success rate for the sample.

This is a measurement, not a performance claim. No GPU is used.

Usage:
    python scripts/benchmark.py --n 40
    python scripts/benchmark.py --n 40 --json
    python scripts/benchmark.py --n 40 --write docs/benchmarking.md
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from simulation.artifacts.store import LocalArtifactStore
from simulation.environments.reach_task import DEFAULT_REACH_SPEC
from simulation.metrics.reach_metrics import compute_metrics
from simulation.runners.episode_runner import EpisodeConfig, run_episode
from simulation.scenarios.generator import generate_suite


def benchmark(n: int, capture_every: int) -> dict:
    import mujoco

    suite = generate_suite(n_scenarios=n, base_seed=1000)
    store = LocalArtifactStore(tempfile.mkdtemp(prefix="simeval-bench-"))

    # Warm-up: one episode to populate caches (JIT-free, but first-call overhead
    # in NumPy/MuJoCo allocation is real and must not pollute the measurement).
    warm = run_episode(
        scenario=suite.scenarios[0],
        policy_name="ik_planner_baseline",
        store=store,
        experiment_id="warmup",
        config=EpisodeConfig(capture_every=capture_every),
    )
    _ = warm.steps

    episodes = []
    serialize_s = 0.0
    inference_s = 0.0
    sim_overhead_s = 0.0
    t_total0 = time.perf_counter()
    for sc in suite.scenarios:
        t0 = time.perf_counter()
        ep = run_episode(
            scenario=sc,
            policy_name="ik_planner_baseline",
            store=store,
            experiment_id="bench",
            config=EpisodeConfig(capture_every=capture_every),
        )
        dt = time.perf_counter() - t0
        episodes.append(ep)
        inference_s += ep.policy_inference_s
        # Simulation-and-overhead time approximated as total minus inference;
        # artifact serialisation is included in the runner's total wall clock.
        sim_overhead_s += dt - ep.policy_inference_s

    total_s = time.perf_counter() - t_total0

    # Artifact serialisation micro-benchmark (isolated from the runner).
    arrays = {
        "qpos": np.random.default_rng(0).normal(size=(400, 4)),
        "qvel": np.random.default_rng(1).normal(size=(400, 4)),
        "ee_pos": np.random.default_rng(2).normal(size=(400, 3)),
    }
    t0 = time.perf_counter()
    ref = store.put_arrays("bench/serialize", arrays)
    serialize_s = time.perf_counter() - t0
    artifact_bytes = (store.root / ref).stat().st_size

    metrics = compute_metrics(episodes, timestep_s=DEFAULT_REACH_SPEC.timestep_s)
    total_steps = sum(e.steps for e in episodes)
    sim_time = total_steps * DEFAULT_REACH_SPEC.timestep_s

    return {
        "machine": {
            "platform": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": __import__("os").cpu_count(),
            "mujoco": mujoco.__version__,
            "numpy": np.__version__,
        },
        "config": {
            "n_episodes": n,
            "capture_every": capture_every,
            "policy": "ik_planner_baseline",
            "task": f"{DEFAULT_REACH_SPEC.task_name} {DEFAULT_REACH_SPEC.task_version}",
            "max_steps": DEFAULT_REACH_SPEC.max_steps,
            "timestep_s": DEFAULT_REACH_SPEC.timestep_s,
        },
        "results": {
            "total_wall_s": total_s,
            "episodes_per_s": n / total_s if total_s > 0 else None,
            "episodes_per_s_incl_warmup": n / (total_s) if total_s > 0 else None,
            "mean_episode_wall_s": total_s / n if n else None,
            "total_sim_time_s": sim_time,
            "real_time_factor": (sim_time / total_s) if total_s > 0 else None,
            "total_steps": total_steps,
            "steps_per_s": (total_steps / total_s) if total_s > 0 else None,
            "policy_inference_total_s": inference_s,
            "policy_inference_mean_ms": (inference_s / n) * 1000.0 if n else None,
            "sim_and_overhead_total_s": sim_overhead_s,
            "artifact_serialize_s": serialize_s,
            "artifact_100k_float_bytes": artifact_bytes,
            "success_rate": metrics.success_rate,
            "n_success": metrics.n_success,
            "n_evaluated": metrics.n_episodes_evaluated,
        },
    }


def render_markdown(result: dict) -> str:
    m = result["machine"]
    c = result["config"]
    r = result["results"]

    def f(value, digits=3):
        return "n/a" if value is None else f"{value:.{digits}f}"

    lines = [
        "# Benchmarking",
        "",
        "> Numbers below are **measured on the development machine**, not claims.",
        "> They are single-process, single-threaded, CPU-only. Re-run",
        "> `python scripts/benchmark.py` to reproduce them on your hardware.",
        "",
        "## Method",
        "",
        "- **Harness:** `scripts/benchmark.py`, one warm-up episode then a timed",
        "  batch through the real `run_episode` pipeline (simulation + policy",
        "  inference + trace recording + grading + artifact serialisation).",
        "- **Timing:** wall-clock via `time.perf_counter`.",
        f"- **Workload:** {c['n_episodes']} scenarios from a seeded suite, policy",
        f"  `{c['policy']}`, `capture_every={c['capture_every']}`, task {c['task']},",
        f"  max {c['max_steps']} steps at {c['timestep_s']} s/step.",
        "- **Unit:** the episode. Throughput counts completed, graded episodes.",
        "- **Excluded:** process start-up, database persistence (measured separately",
        "  below is storage serialisation only), and rendering (off by default).",
        "",
        "## Environment",
        "",
        f"- Platform: {m['platform']} ({m['machine']}), {m['cpu_count']} CPUs",
        f"- Python {m['python']}, NumPy {m['numpy']}, MuJoCo {m['mujoco']}",
        "- No GPU; evaluation is headless.",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Episodes evaluated | {c['n_episodes']} |",
        f"| Total wall clock | {f(r['total_wall_s'])} s |",
        f"| **Episodes / second** | **{f(r['episodes_per_s'])}** |",
        f"| Mean episode wall clock | {f(r['mean_episode_wall_s'], 4)} s |",
        f"| Total simulated time | {f(r['total_sim_time_s'])} s |",
        f"| Real-time factor (sim / wall) | {f(r['real_time_factor'], 1)}x |",
        f"| Control steps / second | {f(r['steps_per_s'], 0)} |",
        f"| Policy inference (mean) | {f(r['policy_inference_mean_ms'], 2)} ms/episode |",
        f"| Sim + overhead total | {f(r['sim_and_overhead_total_s'])} s |",
        f"| Artifact serialize (400x11 array batch) | {f(r['artifact_serialize_s'] * 1000, 3)} ms "
        f"({r['artifact_100k_float_bytes']} bytes on disk) |",
        f"| Success rate (this sample) | {f((r['success_rate'] or 0) * 100, 1)}% "
        f"({r['n_success']}/{r['n_evaluated']}) |",
        "",
        "## Interpretation and limitations",
        "",
        "- Throughput and latency are indicative and machine-load sensitive; they",
        "  are **not** performance guarantees.",
        "- The reach task is lightweight; these figures do not extrapolate to",
        "  contact-rich or rendering-heavy tasks.",
        "- Policy inference dominates wall clock for the baseline IK planner, which",
        "  solves inverse kinematics every step; a cheaper policy increases",
        "  throughput.",
        "- Database persistence is measured in the backend tests, not here.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="SimEval benchmark")
    parser.add_argument("--n", type=int, default=40)
    parser.add_argument("--capture-every", type=int, default=1)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", type=str, default=None, help="write markdown to this path")
    args = parser.parse_args()

    result = benchmark(args.n, args.capture_every)

    if args.write:
        Path(args.write).write_text(render_markdown(result), encoding="utf-8")
        print(f"wrote {args.write}")
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    elif not args.write:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
