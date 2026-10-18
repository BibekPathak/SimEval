"""Baseline reach policy: full inverse-kinematics setpoint planner.

Strategy
--------
Each control step, solve inverse kinematics for the current target position
starting from the neutral configuration, and command the resulting joint
configuration directly to the position servos. This is a "global" planner: it
ignores the current joint state as an IK seed and jumps straight to a resolved
configuration.

This policy is deterministic given the environment state and configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulation.environments.kinematics import damped_least_squares_ik
from simulation.policies.base import Policy, PolicyConfig
from simulation.policies.context import KinematicsContext


@dataclass(frozen=True)
class IKPlannerConfig(PolicyConfig):
    name: str = "ik_planner_baseline"
    version: str = "v1"
    damping: float = 0.05
    iters: int = 300
    step_size: float = 1.0
    max_dq: float = 0.2


class IKPlannerPolicy(Policy[IKPlannerConfig]):
    """Recompute a full IK setpoint each step and command it directly."""

    name = "ik_planner_baseline"
    version = "v1"
    deterministic = True

    def __init__(self, config: IKPlannerConfig, context: KinematicsContext) -> None:
        super().__init__(config)
        self._ctx = context

    def act(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        target_pos = np.asarray(observation["target_pos"], dtype=float)
        q = damped_least_squares_ik(
            self._ctx.mujoco,
            self._ctx.model,
            self._ctx.data,
            target_pos,
            site_name=self._ctx.ee_site_name,
            iters=self.config.iters,
            damping=self.config.damping,
            step_size=self.config.step_size,
            max_dq=self.config.max_dq,
        )
        return self._ctx.clip(q)


__all__ = ["IKPlannerConfig", "IKPlannerPolicy"]
