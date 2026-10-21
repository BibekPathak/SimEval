"""DAgger (Dataset Aggregation) training for the behavior-cloning policy.

Why DAgger
----------
Plain behavior cloning trains only on states the expert visits. Once a learned
policy drifts off that distribution it encounters states it never saw and fails
to recover — the classic compounding-error problem. This was measured directly
on SimEval: single-step BC over 400-step episodes succeeded **0/16** on held-out
scenarios despite low supervised loss.

DAgger fixes the state-distribution mismatch by iterating:

  1. roll out a *mixture* policy (probability ``beta`` of the expert taking
     over, otherwise the current learner) to visit learner-reachable states;
  2. label every visited state with the expert's action;
  3. aggregate the new data with all previous data and retrain.

This is a real, standard imitation-learning algorithm; it is not a rebranded
one-shot fit. The procedure is deterministic for a fixed seed on a fixed machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from simulation.datasets.bc_dataset import featurize
from simulation.environments.reach_env import ReachEnv
from simulation.environments.reach_task import DEFAULT_REACH_SPEC
from simulation.learning.mlp import TrainConfig, TrainHistory, predict, train_mlp
from simulation.policies.registry import build_policy
from simulation.scenarios.generator import ScenarioSuite


@dataclass
class DaggerConfig:
    iterations: int = 4
    #: Probability the expert takes over during data collection, per iteration.
    #: Decays towards ``beta_final`` to emphasise learner-visited states.
    beta_start: float = 1.0
    beta_final: float = 0.5
    train: TrainConfig = field(default_factory=TrainConfig)
    seed: int = 0
    control_stride: int = 2
    max_scenarios: int | None = None


@dataclass
class DaggerReport:
    iterations: int = 0
    total_samples: int = 0
    per_iteration: list[dict[str, Any]] = field(default_factory=list)
    final_train_history: TrainHistory | None = None


def _rollout_mixture(
    suite: ScenarioSuite,
    split: str,
    checkpoint: dict[str, Any] | None,
    *,
    beta: float,
    expert_policy: str,
    control_stride: int,
    rng: np.random.Generator,
    max_scenarios: int | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Collect (features, expert labels) from a beta-mixture rollout."""
    scenarios = suite.scenarios if split == "all" else suite.by_split(split)  # type: ignore[arg-type]
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]

    feats: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for sc in scenarios:
        env = ReachEnv(spec=DEFAULT_REACH_SPEC)
        try:
            env.set_target(np.asarray(sc.target_position, dtype=float))
            obs = env.reset(
                seed=sc.seed,
                initial_qpos=(
                    np.asarray(sc.initial_qpos, dtype=float)
                    if sc.initial_qpos is not None
                    else None
                ),
                qpos_noise=sc.qpos_noise,
            )
            expert = build_policy(expert_policy, None, env.kinematics_context())
            expert.reset()
            for step in range(DEFAULT_REACH_SPEC.max_steps):
                f = featurize(env)
                a_expert = expert.act(obs)
                if checkpoint is None:
                    action = a_expert  # first iteration: pure expert demonstrations
                else:
                    a_learn = predict(checkpoint, f[None, :])[0]
                    action = a_expert if rng.random() < beta else a_learn
                if step % control_stride == 0:
                    feats.append(f)
                    labels.append(np.asarray(a_expert, dtype=np.float64))
                result = env.step(action)
                obs = result.observation
                if result.terminated or result.truncated:
                    break
        finally:
            env.close()
    return np.stack(feats), np.stack(labels)


def train_dagger(
    suite: ScenarioSuite,
    *,
    split: str = "dev+validation",
    expert_policy: str = "ik_planner_baseline",
    config: DaggerConfig | None = None,
) -> tuple[dict[str, Any], DaggerReport]:
    """Run DAgger and return (final_checkpoint, report)."""
    config = config or DaggerConfig()
    rng = np.random.default_rng(config.seed)
    report = DaggerReport()

    # Demonstration collection: allow a combined split by rolling each in turn.
    splits = ["dev", "validation"] if split == "dev+validation" else [split]

    x_all: list[np.ndarray] = []
    y_all: list[np.ndarray] = []
    checkpoint: dict[str, Any] | None = None

    for it in range(config.iterations):
        beta = (
            config.beta_start
            + (config.beta_final - config.beta_start) * (it / max(1, config.iterations - 1))
            if config.iterations > 1
            else config.beta_final
        )
        for sp in splits:
            x_new, y_new = _rollout_mixture(
                suite,
                sp,
                checkpoint,
                beta=beta,
                expert_policy=expert_policy,
                control_stride=config.control_stride,
                rng=rng,
                max_scenarios=config.max_scenarios,
            )
            x_all.append(x_new)
            y_all.append(y_new)

        x = np.concatenate(x_all, axis=0)
        y = np.concatenate(y_all, axis=0)
        checkpoint, history = train_mlp(x, y, config.train)
        report.per_iteration.append(
            {
                "iteration": it,
                "beta": round(beta, 3),
                "samples": int(x.shape[0]),
                "best_val_loss_normalized": history.best_val_loss,
                "best_epoch": history.best_epoch,
            }
        )
        report.final_train_history = history

    assert checkpoint is not None
    report.iterations = config.iterations
    report.total_samples = int(sum(a.shape[0] for a in x_all))
    return checkpoint, report


__all__ = ["DaggerConfig", "DaggerReport", "train_dagger"]
