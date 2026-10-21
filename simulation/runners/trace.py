"""Episode trace recording for the reach task.

A :class:`TraceRecorder` accumulates per-step state during an episode so that
metrics and the grader can be computed from recorded evidence rather than from
values recomputed at the end. It records arrays at a configurable frequency.

Arrays captured per recorded step:
  ``source_step``         env step index (0-based) at capture time
  ``qpos``                joint positions (rad), shape (nq,)
  ``qvel``                joint velocities (rad/s), shape (nq,)
  ``ee_pos``              end-effector site position (m), shape (3,)
  ``target_pos``          target site position (m), shape (3,)
  ``ee_target_dist``      scalar distance (m), shape (1,)
  ``action``              commanded joint positions, shape (nq,)
  ``reward``              scalar reward, shape (1,)
  ``collision``           EE-floor contact count at that step, shape (1,)

Only what is actually observed is stored. Nothing is synthesised.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

#: Canonical set of array names a full trace (with actions) may contain. The API
#: validates client-requested array names against this set so the two layers
#: cannot silently diverge.
RECORDED_ARRAY_NAMES: frozenset[str] = frozenset(
    {
        "source_step",
        "qpos",
        "qvel",
        "ee_pos",
        "target_pos",
        "ee_target_dist",
        "action",
        "reward",
        "collision",
    }
)


@dataclass
class TraceRecorder:
    """Accumulate episode arrays at a fixed capture frequency."""

    capture_every: int = 1
    record_actions: bool = True

    _rows: dict[str, list[np.ndarray]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.capture_every < 1:
            raise ValueError("capture_every must be >= 1")

    def _append(self, key: str, value: np.ndarray) -> None:
        self._rows.setdefault(key, []).append(np.asarray(value, dtype=float).copy())

    def record(
        self,
        *,
        step_index: int,
        observation: dict[str, np.ndarray],
        action: np.ndarray | None,
        reward: float,
        collision: int,
    ) -> bool:
        """Record one step. Returns True if the step was captured.

        The first step (``step_index == 0``) is always captured so that initial
        conditions are preserved even with sparse capture.
        """
        if step_index != 0 and step_index % self.capture_every != 0:
            return False
        self._append("source_step", np.array([step_index]))
        self._append("qpos", observation["qpos"])
        self._append("qvel", observation["qvel"])
        self._append("ee_pos", observation["ee_pos"])
        self._append("target_pos", observation["target_pos"])
        self._append("ee_target_dist", observation["ee_target_dist"])
        self._append("reward", np.array([reward]))
        self._append("collision", np.array([collision]))
        if self.record_actions and action is not None:
            self._append("action", action)
        return True

    @property
    def n_recorded(self) -> int:
        return len(self._rows.get("source_step", []))

    def arrays(self) -> dict[str, np.ndarray]:
        """Return the accumulated arrays as stacked numpy arrays."""
        return {key: np.stack(rows, axis=0) for key, rows in self._rows.items() if rows}

    def as_artifact(self) -> dict[str, np.ndarray]:
        """Alias for :meth:`arrays`, used by the artifact store."""
        return self.arrays()

    def summary(self) -> dict[str, Any]:
        arrays = self.arrays()
        return {
            "n_recorded": self.n_recorded,
            "capture_every": self.capture_every,
            "keys": sorted(arrays),
            "shapes": {k: list(v.shape) for k, v in arrays.items()},
        }


__all__ = ["RECORDED_ARRAY_NAMES", "TraceRecorder"]
