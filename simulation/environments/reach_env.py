"""Gymnasium-style reach environment backed by MuJoCo.

The environment is intentionally simulator-thin: it owns the MuJoCo model/data,
reset/step semantics, termination/truncation, and ground-truth task state. It
does not know about policies, metrics, or persistence.

Action space
------------
The model is actuated by position servos on the four joints. An action is
therefore a length-``nq`` vector of desired joint positions (radians). Policies
return these directly. Actions are validated for finiteness and clipped to the
joint ranges declared in the MJCF.

Observation
-----------
A dict with keys:
  ``qpos``            joint positions (radians), shape (nq,)
  ``qvel``            joint velocities (rad/s), shape (nq,)
  ``ee_pos``          end-effector site position (m), shape (3,)
  ``target_pos``      target site position (m), shape (3,)
  ``ee_target_vec``   target - ee_pos (m), shape (3,)
  ``ee_target_dist``  Euclidean distance (m), scalar
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from simulation.environments.reach_mjcf import MJCF_REACH
from simulation.environments.reach_task import DEFAULT_REACH_SPEC, ReachTaskSpec

try:  # pragma: no cover - import guard exercised only in broken environments
    import mujoco
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "MuJoCo is required for simulation. Install it with `uv pip install 'mujoco>=3.2.3,<4.0'`."
    ) from exc


@dataclass
class StepResult:
    observation: dict[str, np.ndarray]
    reward: float
    terminated: bool
    truncated: bool
    info: dict[str, Any]


class ReachEnv:
    """Seeded, reproducible reach task environment."""

    metadata: ClassVar[dict[str, Any]] = {"render_modes": ["rgb_array"], "render_fps": 40}

    def __init__(self, spec: ReachTaskSpec | None = None) -> None:
        self.spec = spec or DEFAULT_REACH_SPEC
        self.model = mujoco.MjModel.from_xml_string(MJCF_REACH)
        self.data = mujoco.MjData(self.model)

        self._ee_site_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_SITE, "ee_site")
        self._target_site_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_SITE, "target_site"
        )
        self._target_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "target")
        self._floor_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "floor")
        self._ee_geom_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "ee_g")

        self.action_dim = int(self.model.nq)
        self.nq = int(self.model.nq)

        # Joint limits used to clip actions. Unlimited joints fall back to +-pi.
        self._ctrl_min = np.where(
            self.model.jnt_limited[: self.model.nq] == 1,
            self.model.jnt_range[: self.model.nq, 0],
            -np.pi,
        ).astype(float)
        self._ctrl_max = np.where(
            self.model.jnt_limited[: self.model.nq] == 1,
            self.model.jnt_range[: self.model.nq, 1],
            np.pi,
        ).astype(float)

        self._step_count = 0
        self._success_streak = 0
        self._rng = np.random.default_rng(0)
        self._target_pos = np.zeros(3, dtype=float)
        self._initial_qpos = np.zeros(self.nq, dtype=float)
        self._renderer: Any | None = None

    # ------------------------------------------------------------------ reset
    def set_target(self, position: np.ndarray) -> None:
        """Move the goal marker. Used by scenario generation before reset."""
        pos = np.asarray(position, dtype=float).reshape(3)
        if not np.all(np.isfinite(pos)):
            raise ValueError(f"target position must be finite, got {position!r}")
        self.model.body_pos[self._target_body_id] = pos
        self._target_pos = pos.copy()

    def reset(
        self,
        *,
        seed: int,
        initial_qpos: np.ndarray | None = None,
        qpos_noise: float = 0.0,
    ) -> dict[str, np.ndarray]:
        """Reset the environment with an explicit seed.

        Args:
            seed: Seed for any stochastic initialisation. Same seed + same
                scenario => identical trajectory.
            initial_qpos: Explicit starting joint configuration. Defaults to the
                MJCF ``qpos0``.
            qpos_noise: Uniform per-joint noise magnitude added to the initial
                configuration. 0.0 keeps the reset fully deterministic.
        """
        self._rng = np.random.default_rng(seed)
        mujoco.mj_resetData(self.model, self.data)

        base = (
            np.array(self.data.qpos, dtype=float)
            if initial_qpos is None
            else np.asarray(initial_qpos, dtype=float).reshape(self.nq).copy()
        )
        if qpos_noise > 0.0:
            base = base + self._rng.uniform(-qpos_noise, qpos_noise, size=self.nq)
        self.data.qpos[:] = np.clip(base, self._ctrl_min, self._ctrl_max)
        self.data.qvel[:] = 0.0
        self._initial_qpos = np.array(self.data.qpos, dtype=float)

        mujoco.mj_forward(self.model, self.data)

        self._step_count = 0
        self._success_streak = 0
        return self._observation()

    # ------------------------------------------------------------------- step
    def step(self, action: np.ndarray) -> StepResult:
        action = np.asarray(action, dtype=float).reshape(-1)
        if action.shape[0] != self.action_dim:
            raise ValueError(f"action must have shape ({self.action_dim},), got {action.shape}")
        finite = bool(np.all(np.isfinite(action)))
        if not finite:
            # Non-finite actions are a hard error; the runner records them as a
            # numerical failure rather than silently continuing.
            self._step_count += 1
            obs = self._observation()
            return StepResult(
                observation=obs,
                reward=0.0,
                terminated=True,
                truncated=False,
                info={
                    "invalid_action": True,
                    "reason": "non_finite_action",
                    "step_count": self._step_count,
                },
            )

        clipped = np.clip(action, self._ctrl_min, self._ctrl_max)
        self.data.ctrl[:] = clipped
        mujoco.mj_step(self.model, self.data)
        self._step_count += 1

        obs = self._observation()
        dist = float(obs["ee_target_dist"][0])

        if dist < self.spec.success_distance_m:
            self._success_streak += 1
        else:
            self._success_streak = 0

        terminated = self._success_streak >= self.spec.success_dwell_steps
        truncated = self._step_count >= self.spec.max_steps

        reward = 1.0 if terminated else 0.0
        info = {
            "ee_target_dist": dist,
            "success_streak": self._success_streak,
            "step_count": self._step_count,
            "collision": self.collision_count(),
        }
        return StepResult(obs, reward, terminated, truncated, info)

    # ------------------------------------------------------------ inspection
    def _observation(self) -> dict[str, np.ndarray]:
        ee_pos = np.array(self.data.site_xpos[self._ee_site_id], dtype=float)
        target_pos = np.array(self.data.site_xpos[self._target_site_id], dtype=float)
        vec = target_pos - ee_pos
        return {
            "qpos": np.array(self.data.qpos, dtype=float),
            "qvel": np.array(self.data.qvel, dtype=float),
            "ee_pos": ee_pos,
            "target_pos": target_pos,
            "ee_target_vec": vec,
            "ee_target_dist": np.array([float(np.linalg.norm(vec))]),
        }

    def observation(self) -> dict[str, np.ndarray]:
        return self._observation()

    def ee_position(self) -> np.ndarray:
        return np.array(self.data.site_xpos[self._ee_site_id], dtype=float)

    def target_position(self) -> np.ndarray:
        return np.array(self.data.site_xpos[self._target_site_id], dtype=float)

    def ee_target_distance(self) -> float:
        return float(np.linalg.norm(self.ee_position() - self.target_position()))

    def joint_positions(self) -> np.ndarray:
        return np.array(self.data.qpos[: self.nq], dtype=float)

    def joint_velocities(self) -> np.ndarray:
        return np.array(self.data.qvel[: self.nq], dtype=float)

    def collision_count(self) -> int:
        """Number of active EE-vs-floor contact points.

        Only the end-effector sphere and the floor are collidable geoms in the
        model, so any contact here is an EE-floor contact by construction.
        """
        count = 0
        for i in range(self.data.ncon):
            c = self.data.contact[i]
            pair = {int(c.geom1), int(c.geom2)}
            if pair == {self._ee_geom_id, self._floor_geom_id}:
                count += 1
        return count

    @property
    def step_count(self) -> int:
        return self._step_count

    def kinematics_context(self) -> Any:
        """Expose live model/data and joint limits for kinematics-based policies."""
        from simulation.policies.context import KinematicsContext

        return KinematicsContext(
            mujoco=mujoco,
            model=self.model,
            data=self.data,
            ee_site_name="ee_site",
            action_dim=self.action_dim,
            ctrl_min=self._ctrl_min,
            ctrl_max=self._ctrl_max,
            ee_site_id=int(self._ee_site_id),
        )

    # ---------------------------------------------------------------- render
    def render_frame(self, height: int = 240, width: int = 320) -> np.ndarray:
        """Render an RGB frame. Requires a working MuJoCo GL backend."""
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, height=height, width=width)
        self._renderer.update_scene(self.data)
        return np.asarray(self._renderer.render())

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


__all__ = ["ReachEnv", "StepResult"]
