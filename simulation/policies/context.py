"""Shared context passed to policies that need access to the simulator.

Policies that use kinematics or contact information need the live MuJoCo
``model`` and ``data``. This small container avoids coupling the policy
interface to a specific environment class while still giving policies what they
need. Learned policies that only consume observations can ignore it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class KinematicsContext:
    """Live simulator handles plus cached joint limits for action clipping."""

    mujoco: Any
    model: Any
    data: Any
    ee_site_name: str = "ee_site"
    action_dim: int = 4
    ctrl_min: Any = None
    ctrl_max: Any = None
    ee_site_id: int = -1

    def clip(self, action: Any) -> Any:
        import numpy as np

        if self.ctrl_min is None or self.ctrl_max is None:
            return action
        return np.clip(action, self.ctrl_min, self.ctrl_max)


class SupportsKinematics(Protocol):
    """Environment protocol exposing what policies require."""

    def kinematics_context(self) -> KinematicsContext: ...


__all__ = ["KinematicsContext", "SupportsKinematics"]
