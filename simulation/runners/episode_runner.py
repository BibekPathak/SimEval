"""Episode runner: executes one scenario for one policy end to end.

Responsibilities:

1. Build the environment and policy.
2. Reset the environment with the scenario seed and initial conditions.
3. Step the policy until termination/truncation/safety limit.
4. Record observations, actions, and physical state via a :class:`TraceRecorder`.
5. Compute episode-level aggregates from the recorded trace.
6. Persist the trace to the artifact store.
7. Grade the episode with the task grader.
8. Return a fully-populated :class:`EpisodeResult`.

Failure handling is explicit: simulator exceptions, non-finite state, and
non-finite actions produce infrastructure outcomes and are never counted as
successes. The environment is always closed in a ``finally`` block.
"""

from __future__ import annotations

import time
import traceback
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np

from simulation.artifacts.store import ArtifactStore, LocalArtifactStore
from simulation.environments.reach_env import ReachEnv
from simulation.environments.reach_task import DEFAULT_REACH_SPEC, ReachTaskSpec
from simulation.graders.reach_grader import GradeInputs, get_grader
from simulation.policies.base import Policy
from simulation.policies.registry import build_policy
from simulation.runners.outcome import EpisodeResult, Outcome, finite_float
from simulation.runners.trace import TraceRecorder
from simulation.scenarios.generator import Scenario


@dataclass
class EpisodeConfig:
    """Runtime configuration for a single episode execution."""

    capture_every: int = 1
    persist_artifacts: bool = True
    timeout_s: float | None = 60.0
    policy_config: dict[str, Any] | None = None


def run_episode(
    *,
    scenario: Scenario,
    policy_name: str,
    spec: ReachTaskSpec | None = None,
    config: EpisodeConfig | None = None,
    store: ArtifactStore | None = None,
    experiment_id: str = "experiment",
    episode_id: str | None = None,
) -> EpisodeResult:
    """Execute one episode and return its graded, persisted result."""
    spec = spec or DEFAULT_REACH_SPEC
    config = config or EpisodeConfig()
    episode_id = episode_id or f"{experiment_id}-{scenario.scenario_id}-{uuid.uuid4().hex[:8]}"

    env: ReachEnv | None = None
    recorder = TraceRecorder(capture_every=config.capture_every)

    wall_start = time.perf_counter()
    policy_inference_total = 0.0
    steps = 0
    terminated = False
    truncated = False
    success = False
    return_sum = 0.0
    invalid_action = False
    numerical_failure = False
    simulator_error = False
    error_message: str | None = None
    initial_dist = float("nan")
    min_dist = float("inf")
    final_dist = float("nan")
    collision_steps = 0
    max_collision_count = 0
    policy: Policy | None = None
    artifact_ref: str | None = None
    trace_finite = True

    try:
        env = ReachEnv(spec=spec)
        env.set_target(np.asarray(scenario.target_position, dtype=float))
        obs = env.reset(
            seed=scenario.seed,
            initial_qpos=(
                np.asarray(scenario.initial_qpos, dtype=float)
                if scenario.initial_qpos is not None
                else None
            ),
            qpos_noise=scenario.qpos_noise,
        )
        policy = build_policy(policy_name, config.policy_config, env.kinematics_context())
        policy.reset()

        initial_dist = env.ee_target_distance()
        min_dist = initial_dist
        coll = env.collision_count()
        max_collision_count = max(max_collision_count, coll)
        if coll > 0:
            collision_steps += 1
        recorder.record(
            step_index=0,
            observation=obs,
            action=None,
            reward=0.0,
            collision=coll,
        )

        for step_index in range(1, spec.max_steps + 1):
            if (
                config.timeout_s is not None
                and (time.perf_counter() - wall_start) > config.timeout_s
            ):
                truncated = True
                break

            t0 = time.perf_counter()
            action = policy.act(obs)
            policy_inference_total += time.perf_counter() - t0

            result = env.step(action)
            steps = step_index
            obs = result.observation

            if result.info.get("invalid_action"):
                invalid_action = True
                break

            if not np.all(np.isfinite(obs["qpos"])) or not np.all(np.isfinite(obs["ee_pos"])):
                numerical_failure = True
                break

            return_sum += float(result.reward)
            dist = env.ee_target_distance()
            min_dist = min(min_dist, dist)
            coll = env.collision_count()
            max_collision_count = max(max_collision_count, coll)
            if coll > 0:
                collision_steps += 1

            recorder.record(
                step_index=step_index,
                observation=obs,
                action=action,
                reward=float(result.reward),
                collision=coll,
            )

            if result.terminated:
                terminated = True
                success = True
                break
            if result.truncated:
                truncated = True
                break

        final_dist = env.ee_target_distance()

        if config.persist_artifacts:
            store = store or LocalArtifactStore("artifacts")
            artifact_ref = store.put_arrays(
                f"{experiment_id}/episodes/{episode_id}", recorder.as_artifact()
            )
    except Exception as exc:
        simulator_error = True
        error_message = f"{type(exc).__name__}: {exc}"
        traceback_str = traceback.format_exc()
        # Preserve a bounded traceback for debugging without unbounded logs.
        error_message = f"{error_message}\n{traceback_str[-2000:]}"
        if steps == 0:
            final_dist = initial_dist
    finally:
        try:
            if env is not None:
                env.close()
        except Exception:
            pass

    wall_clock_s = time.perf_counter() - wall_start

    trace_finite = _trace_finite(recorder)

    grade_inputs = GradeInputs(
        terminated=terminated,
        truncated=truncated,
        success=success,
        steps=steps,
        max_steps=spec.max_steps,
        initial_ee_target_dist_m=_safe(initial_dist),
        final_ee_target_dist_m=_safe(final_dist),
        min_ee_target_dist_m=_safe(min_dist if np.isfinite(min_dist) else initial_dist),
        success_distance_m=spec.success_distance_m,
        collision_steps=collision_steps,
        max_collision_count=max_collision_count,
        invalid_action=invalid_action,
        numerical_failure=numerical_failure,
        simulator_error=simulator_error,
        error_message=error_message,
        trace_finite=trace_finite,
    )
    grade = get_grader(scenario.task_name).grade(grade_inputs)

    episode = EpisodeResult(
        episode_id=episode_id,
        experiment_id=experiment_id,
        scenario_id=scenario.scenario_id,
        policy_name=policy_name,
        policy_version=(policy.version if policy is not None else "unknown"),
        task_name=scenario.task_name,
        task_version=scenario.task_version,
        seed=scenario.seed,
        split=scenario.split,
        difficulty=scenario.difficulty,
        success=grade.success and grade.outcome == Outcome.SUCCESS,
        outcome=grade.outcome.value,
        failure_category=grade.failure_category,
        explanation=grade.explanation,
        rule=grade.rule,
        steps=steps,
        wall_clock_s=wall_clock_s,
        sim_time_s=steps * spec.timestep_s,
        return_sum=return_sum,
        min_ee_target_dist_m=finite_float(grade_inputs.min_ee_target_dist_m, float("nan"))
        or float("nan"),
        final_ee_target_dist_m=finite_float(grade_inputs.final_ee_target_dist_m, float("nan"))
        or float("nan"),
        initial_ee_target_dist_m=finite_float(grade_inputs.initial_ee_target_dist_m, float("nan"))
        or float("nan"),
        collision_steps=collision_steps,
        max_collision_count=max_collision_count,
        policy_inference_s=policy_inference_total,
        metrics=_episode_metrics(
            steps=steps,
            wall_clock_s=wall_clock_s,
            sim_time_s=steps * spec.timestep_s,
            return_sum=return_sum,
            collision_steps=collision_steps,
            policy_inference_total=policy_inference_total,
            spec=spec,
        ),
        artifact_ref=artifact_ref,
        error=error_message,
    )
    return episode


def _episode_metrics(
    *,
    steps: int,
    wall_clock_s: float,
    sim_time_s: float,
    return_sum: float,
    collision_steps: int,
    policy_inference_total: float,
    spec: ReachTaskSpec,
) -> dict[str, Any]:
    return {
        "steps": steps,
        "wall_clock_s": wall_clock_s,
        "sim_time_s": sim_time_s,
        "real_time_factor": (sim_time_s / wall_clock_s) if wall_clock_s > 0 else None,
        "return_sum": return_sum,
        "collision_steps": collision_steps,
        "policy_inference_s": policy_inference_total,
        "policy_inference_ms_per_step": (
            (policy_inference_total / steps) * 1000.0 if steps > 0 else None
        ),
        "timestep_s": spec.timestep_s,
    }


def _safe(value: float) -> float:
    return float(value) if value is not None and np.isfinite(value) else float("nan")


def _trace_finite(recorder: TraceRecorder) -> bool:
    try:
        for arr in recorder.as_artifact().values():
            if not np.all(np.isfinite(np.asarray(arr, dtype=float))):
                return False
    except (ValueError, TypeError):
        return False
    return True


__all__ = ["EpisodeConfig", "run_episode"]
