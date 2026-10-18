"""Task specification constants for the SimEval reach task.

These values define the task objective and are intentionally versioned so that
scenario suites and experiments can record which task definition they used.
Changing a success threshold or episode length invalidates comparisons across
versions, so the version string must be bumped when any of these change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReachTaskSpec:
    """Immutable definition of the reach task objective."""

    task_name: str = "reach"
    task_version: str = "v1"

    #: Success when the end-effector site is within this distance of the target
    #: site at the moment of success check.
    success_distance_m: float = 0.05

    #: Number of consecutive steps the end effector must remain within the
    #: success distance before the episode is considered successful. Requiring
    #: dwell prevents counting a transient fly-through as success.
    success_dwell_steps: int = 10

    #: Maximum number of control steps before truncation.
    max_steps: int = 400

    #: Simulation timestep in seconds (must match the MJCF ``option``).
    timestep_s: float = 0.005

    #: Contact is counted as a collision event when the end-effector sphere
    #: touches the floor plane. Only EE-vs-floor contacts are collidable in the
    #: model, so this definition is exact for this task.
    collision_is_floor_contact: bool = True

    @property
    def max_episode_time_s(self) -> float:
        return self.max_steps * self.timestep_s


DEFAULT_REACH_SPEC = ReachTaskSpec()

__all__ = ["DEFAULT_REACH_SPEC", "ReachTaskSpec"]
