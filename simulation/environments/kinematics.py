"""Damped least-squares inverse kinematics helper for the reach arm.

Kept separate from both the environment and the policies so that multiple
policies can share the same numerical routine while differing in strategy.

The routine is deterministic: it starts from a fixed seed configuration and
takes fixed-size steps toward the target using the damped pseudo-inverse of the
site Jacobian.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def damped_least_squares_ik(
    mujoco: Any,
    model: Any,
    data: Any,
    target_pos: np.ndarray,
    site_name: str = "ee_site",
    *,
    iters: int = 300,
    damping: float = 0.05,
    step_size: float = 1.0,
    max_dq: float = 0.2,
    q_init: np.ndarray | None = None,
    tol: float = 1e-4,
) -> np.ndarray:
    """Resolve joint positions placing ``site_name`` as close as possible to
    ``target_pos``.

    Args:
        mujoco: The imported ``mujoco`` module.
        model: ``MjModel``.
        data: ``MjData`` (mutated during iteration, restored afterwards).
        target_pos: Desired Cartesian position of the site (m).
        iters: Maximum iterations.
        damping: Levenberg-Marquardt damping (lambda).
        step_size: Scalar gain on each update.
        max_dq: Per-iteration joint step clamp (rad).
        q_init: Starting configuration. Defaults to the model ``qpos0``.
        tol: Cartesian convergence tolerance (m).

    Returns:
        A length-``nq`` joint-position vector.
    """
    target_pos = np.asarray(target_pos, dtype=float).reshape(3)
    site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, site_name)
    nv = int(model.nv)

    saved_qpos = np.array(data.qpos, dtype=float)
    saved_qvel = np.array(data.qvel, dtype=float)

    q = (
        np.array(data.qpos, dtype=float)
        if q_init is None
        else np.asarray(q_init, dtype=float).reshape(model.nq).copy()
    )
    data.qpos[:] = q
    data.qvel[:] = 0.0

    jacp = np.zeros((3, nv))
    eye = np.eye(3)
    for _ in range(iters):
        mujoco.mj_forward(model, data)
        err = target_pos - np.array(data.site_xpos[site_id], dtype=float)
        if float(np.linalg.norm(err)) < tol:
            break
        mujoco.mj_jacSite(model, data, jacp, None, site_id)
        dq = jacp.T @ np.linalg.solve(jacp @ jacp.T + (damping**2) * eye, step_size * err)
        q = q + np.clip(dq, -max_dq, max_dq)
        data.qpos[:] = q

    # Restore caller state.
    data.qpos[:] = saved_qpos
    data.qvel[:] = saved_qvel
    mujoco.mj_forward(model, data)
    return q


__all__ = ["damped_least_squares_ik"]
