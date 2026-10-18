"""Candidate reach policy: incremental resolved-rate controller.

Strategy
--------
Each control step, take a bounded local step in joint space toward the target
by applying the damped pseudo-inverse of the site Jacobian to the current
end-effector error, seeded from the *current* joint configuration. The commanded
joint setpoint is the current joint positions plus that bounded increment. This
is a "local" feedback controller: it tracks the target smoothly and re-plans
every step from where the arm actually is.

It differs from the baseline planner in algorithm, not merely in parameters:
the baseline performs a fresh global IK solve from a neutral seed and jumps to
the result, while this controller advances incrementally from the live state.

This policy is deterministic given the environment state and configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simulation.policies.base import Policy, PolicyConfig
from simulation.policies.context import KinematicsContext


@dataclass(frozen=True)
class ResolvedRateConfig(PolicyConfig):
    name: str = "resolved_rate_candidate"
    version: str = "v1"
    gain: float = 0.35
    max_dq: float = 0.08
    damping: float = 0.1


class ResolvedRatePolicy(Policy[ResolvedRateConfig]):
    """Incremental Jacobian-feedback controller from the live joint state."""

    name = "resolved_rate_candidate"
    version = "v1"
    deterministic = True

    def __init__(self, config: ResolvedRateConfig, context: KinematicsContext) -> None:
        super().__init__(config)
        self._ctx = context
        self._jacp = np.zeros((3, int(context.model.nv)))

    def act(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        mujoco = self._ctx.mujoco
        model = self._ctx.model
        data = self._ctx.data

        ee_pos = np.asarray(observation["ee_pos"], dtype=float)
        target_pos = np.asarray(observation["target_pos"], dtype=float)
        err = target_pos - ee_pos

        mujoco.mj_jacSite(model, data, self._jacp, None, self._ctx.ee_site_id)
        damping = self.config.damping
        dq = self._jacp.T @ np.linalg.solve(
            self._jacp @ self._jacp.T + (damping**2) * np.eye(3),
            self.config.gain * err,
        )
        dq = np.clip(dq, -self.config.max_dq, self.config.max_dq)

        current = np.asarray(observation["qpos"], dtype=float)
        return self._ctx.clip(current + dq)


__all__ = ["ResolvedRateConfig", "ResolvedRatePolicy"]
