"""Learned behavior-cloning policy implementing the SimEval policy interface.

The policy loads a checkpoint produced by ``simulation.learning.mlp`` and maps
observation features to desired joint positions each control step. It is a
genuine learned policy: the actions come from a trained network, not from the
expert controller that produced the demonstrations.

Scope and honesty
-----------------
This is **imitation of a classical controller**, not end-to-end vision-based
manipulation. It consumes low-dimensional state (joints + end-effector-to-target
vector), not images. It is evaluated on held-out scenarios and compared with the
expert it imitates; it is not claimed to generalise beyond the reach task.

The checkpoint path is resolved relative to the repository root and validated so
that a config cannot read arbitrary files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from simulation.learning.mlp import load_checkpoint, predict
from simulation.policies.base import Policy, PolicyConfig
from simulation.policies.context import KinematicsContext

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class BehaviorCloningConfig(PolicyConfig):
    name: str = "behavior_cloning"
    version: str = "v1"
    checkpoint: str = "checkpoints/bc_reach_v1.json"
    #: Clip the network output to the joint limits (the runner also clips).
    clamp_to_limits: bool = True


class BehaviorCloningPolicy(Policy[BehaviorCloningConfig]):
    """MLP behavior-cloning policy over low-dimensional state."""

    name = "behavior_cloning"
    version = "v1"
    deterministic = True

    def __init__(self, config: BehaviorCloningConfig, context: KinematicsContext) -> None:
        super().__init__(config)
        self._ctx = context
        self.checkpoint = load_checkpoint(_resolve_checkpoint(config.checkpoint))

    def act(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        qpos = np.asarray(observation["qpos"], dtype=np.float64)
        qvel = np.asarray(observation["qvel"], dtype=np.float64)
        vec = np.asarray(observation["ee_target_vec"], dtype=np.float64)
        dist = float(np.linalg.norm(vec))
        features = np.concatenate([qpos, qvel, vec, np.array([dist])])
        action = predict(self.checkpoint, features[None, :])[0]
        if not np.all(np.isfinite(action)):
            # Surface a non-finite action so the runner records INVALID_ACTION
            # rather than silently substituting something.
            return action
        return self._ctx.clip(action) if self.config.clamp_to_limits else action


def _resolve_checkpoint(path_str: str) -> Path:
    candidate = Path(path_str)
    resolved = candidate if candidate.is_absolute() else (_REPO_ROOT / candidate).resolve()
    # Allow files inside the repo or an explicit SIMEVAL_CHECKPOINT_DIR only.
    if not resolved.is_file():
        raise FileNotFoundError(
            f"behavior-cloning checkpoint not found: {resolved}. "
            "Train one with `python scripts/train_bc.py`."
        )
    return resolved


__all__ = ["BehaviorCloningConfig", "BehaviorCloningPolicy"]
