#!/usr/bin/env python3
"""Headless MuJoCo smoke test for SimEval (Milestone 1).

This script is a *capability probe*, not an evaluation. It verifies that the
environment can run real physics simulation headlessly before any product code
is layered on top of it. It intentionally does NOT fake any results: every
printed number is read back from the MuJoCo data structures after real
integration steps.

It checks, in order:
  1. MuJoCo imports and reports a version.
  2. A small MJCF model parses.
  3. Deterministic reset + stepping produces finite, reproducible state.
  4. Ground-truth geometric quantities (end-effector / target distance) can be
     read from the simulator.
  5. Contact information is observable.
  6. Optional offscreen rendering works (reported as skipped, not failed, if no
     GL backend is available).

Exit code is non-zero if a hard requirement fails. Rendering is soft-optional.

Usage:
    python scripts/smoke_sim.py
    python scripts/smoke_sim.py --render
    python scripts/smoke_sim.py --json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

MJCF_REACH = """
<mujoco model="simeval_reach_smoke">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="0.005" integrator="implicitfast"/>
  <default>
    <geom rgba="0.55 0.58 0.62 1" contype="1" conaffinity="1"/>
  </default>
  <worldbody>
    <light pos="0 0 3" dir="0 0 -1" diffuse="0.8 0.8 0.8"/>
    <geom name="floor" type="plane" size="2 2 0.1" rgba="0.22 0.23 0.25 1"
          pos="0 0 0" contype="1" conaffinity="1"/>
    <body name="base" pos="0 0 0">
      <geom name="base_g" contype="0" conaffinity="0" type="cylinder" size="0.05 0.03" pos="0 0 0.03"/>
      <body name="link1" pos="0 0 0.06" gravcomp="1">
        <joint name="j1" type="hinge" axis="0 0 1" range="-3.14 3.14"/>
        <geom name="link1_g" contype="0" conaffinity="0" type="capsule" fromto="0 0 0 0 0 0.30" size="0.025"/>
        <body name="link2" pos="0 0 0.30" quat="0.9238795 0 0.3826834 0" gravcomp="1">
          <joint name="j2" type="hinge" axis="0 1 0" range="-1.6 1.6"/>
          <geom name="link2_g" contype="0" conaffinity="0" type="capsule" fromto="0 0 0 0 0 0.25" size="0.022"/>
          <body name="link3" pos="0 0 0.25" quat="0.9238795 0 0.3826834 0" gravcomp="1">
            <joint name="j3" type="hinge" axis="0 1 0" range="-1.6 1.6"/>
            <geom name="link3_g" contype="0" conaffinity="0" type="capsule" fromto="0 0 0 0 0 0.20" size="0.02"/>
            <body name="ee" pos="0 0 0.20" gravcomp="1">
              <site name="ee_site" pos="0 0 0"/>
              <geom name="ee_g" type="sphere" size="0.03" rgba="0.85 0.35 0.30 1"/>
            </body>
          </body>
        </body>
      </body>
    </body>
    <body name="target" pos="0.2 0 0.55">
      <geom name="target_g" type="sphere" size="0.035" rgba="0.30 0.80 0.40 1"
            contype="0" conaffinity="0"/>
      <site name="target_site" pos="0 0 0"/>
    </body>
  </worldbody>
  <actuator>
    <position name="a1" joint="j1" kp="200" kv="20"/>
    <position name="a2" joint="j2" kp="200" kv="20"/>
    <position name="a3" joint="j3" kp="200" kv="20"/>
  </actuator>
</mujoco>
"""

SUCCESS_DISTANCE_M = 0.05
MAX_STEPS = 400


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class SmokeReport:
    ok: bool = False
    python: str = ""
    platform: str = ""
    mujoco_version: str = ""
    mjcf_hash: str = ""
    nq: int = 0
    nu: int = 0
    nbody: int = 0
    ngeom: int = 0
    steps: int = 0
    seed: int = 0
    # Determinism probe
    det_qpos_a: list[float] = field(default_factory=list)
    det_qpos_b: list[float] = field(default_factory=list)
    det_max_abs_diff: float = 0.0
    deterministic: bool = False
    # Task geometry
    initial_ee_target_distance_m: float = 0.0
    final_ee_target_distance_m: float = 0.0
    min_ee_target_distance_m: float = 0.0
    success_threshold_m: float = SUCCESS_DISTANCE_M
    success: bool = False
    # Contacts
    contact_count_final: int = 0
    # Rendering
    render_requested: bool = False
    render_ok: bool = False
    render_detail: str = "not attempted"
    render_mean_pixel: float = 0.0
    checks: list[CheckResult] = field(default_factory=list)


def _solve_ik(
    mujoco: Any, model: Any, target_pos: np.ndarray, iters: int = 2000, lam: float = 0.05
) -> np.ndarray:
    """Damped least-squares inverse kinematics for the end-effector site.

    Returns a joint-position vector whose forward kinematics places the
    ``ee_site`` as close as possible to ``target_pos``. Deterministic: it starts
    from a fixed neutral configuration and takes fixed-size steps.
    """
    data = mujoco.MjData(model)
    q = np.zeros(model.nq, dtype=float)
    data.qpos[:] = q
    ee_site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "ee_site")
    jacp = np.zeros((3, model.nv))
    eye = np.eye(3)
    for _ in range(iters):
        mujoco.mj_forward(model, data)
        err = target_pos - np.array(data.site_xpos[ee_site_id], dtype=float)
        if float(np.linalg.norm(err)) < 1e-4:
            break
        mujoco.mj_jacSite(model, data, jacp, None, ee_site_id)
        dq = jacp.T @ np.linalg.solve(jacp @ jacp.T + (lam**2) * eye, err)
        q = q + np.clip(dq, -0.2, 0.2)
        data.qpos[:] = q
    return q


def _rollout(mujoco: Any, model: Any, seed: int, steps: int) -> dict[str, Any]:
    """Run a deterministic PD-style rollout and return observed quantities."""
    rng = np.random.default_rng(seed)
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)

    ee_site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "ee_site")
    target_site_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "target_site")

    # Tiny per-seed jitter on the *initial* configuration makes the seed
    # meaningful without changing the task objective.
    data.qpos[:] += rng.uniform(-0.01, 0.01, size=model.nq)
    mujoco.mj_forward(model, data)

    target_pos = np.array(data.site_xpos[target_site_id], dtype=float)
    initial_dist = float(np.linalg.norm(data.site_xpos[ee_site_id] - target_pos))
    min_dist = initial_dist

    # Resolve a joint configuration that places the end effector on the target
    # using damped least-squares IK, then command it through the position
    # actuators. This is a stable, fully deterministic reference behaviour.
    q_ref = _solve_ik(mujoco, model, target_pos)
    q_lo = model.jnt_range[: model.nq, 0].copy()
    q_hi = model.jnt_range[: model.nq, 1].copy()
    unlimited = model.jnt_limited[: model.nq] == 0
    q_lo[unlimited], q_hi[unlimited] = -np.inf, np.inf
    q_ref = np.clip(q_ref, q_lo, q_hi)

    for _ in range(steps):
        data.ctrl[:] = q_ref
        mujoco.mj_step(model, data)
        if not np.all(np.isfinite(data.qpos)):
            break
        ee = np.array(data.site_xpos[ee_site_id], dtype=float)
        min_dist = min(min_dist, float(np.linalg.norm(ee - target_pos)))

    final_ee = np.array(data.site_xpos[ee_site_id], dtype=float)
    final_dist = float(np.linalg.norm(final_ee - target_pos))
    return {
        "qpos": [float(x) for x in data.qpos],
        "final_dist": final_dist,
        "initial_dist": initial_dist,
        "min_dist": float(min_dist),
        "ncon": int(data.ncon),
    }


def run(render: bool = False) -> SmokeReport:
    rep = SmokeReport(
        python=platform.python_version(),
        platform=f"{platform.system()} {platform.release()} ({platform.machine()})",
        render_requested=render,
    )

    import hashlib

    rep.mjcf_hash = hashlib.sha256(MJCF_REACH.encode()).hexdigest()[:16]

    try:
        import mujoco
    except Exception as exc:  # pragma: no cover - environment dependent
        rep.checks.append(CheckResult("import_mujoco", False, f"{type(exc).__name__}: {exc}"))
        return rep

    rep.mujoco_version = mujoco.__version__
    rep.checks.append(CheckResult("import_mujoco", True, f"mujoco {mujoco.__version__}"))

    try:
        model = mujoco.MjModel.from_xml_string(MJCF_REACH)
    except Exception as exc:  # pragma: no cover
        rep.checks.append(CheckResult("parse_mjcf", False, f"{type(exc).__name__}: {exc}"))
        return rep

    rep.nq = int(model.nq)
    rep.nu = int(model.nu)
    rep.nbody = int(model.nbody)
    rep.ngeom = int(model.ngeom)
    rep.steps = MAX_STEPS
    rep.seed = 1234
    rep.checks.append(
        CheckResult("parse_mjcf", True, f"nq={model.nq} nu={model.nu} nbody={model.nbody}")
    )

    # --- Determinism: same seed twice ---
    a = _rollout(mujoco, model, seed=rep.seed, steps=MAX_STEPS)
    b = _rollout(mujoco, model, seed=rep.seed, steps=MAX_STEPS)
    diff = float(np.max(np.abs(np.array(a["qpos"]) - np.array(b["qpos"]))))
    rep.det_qpos_a = a["qpos"]
    rep.det_qpos_b = b["qpos"]
    rep.det_max_abs_diff = diff
    rep.deterministic = diff == 0.0
    rep.checks.append(
        CheckResult(
            "determinism",
            rep.deterministic,
            f"max|qpos_a - qpos_b| = {diff:.3e} over {MAX_STEPS} steps",
        )
    )

    finite = bool(np.all(np.isfinite(a["qpos"])))
    rep.checks.append(CheckResult("finite_state", finite, f"all qpos finite: {finite}"))

    # --- Task geometry ---
    rep.initial_ee_target_distance_m = a["initial_dist"]
    rep.final_ee_target_distance_m = a["final_dist"]
    rep.min_ee_target_distance_m = a["min_dist"]
    rep.success = a["final_dist"] < SUCCESS_DISTANCE_M
    improved = a["final_dist"] < a["initial_dist"]
    rep.checks.append(
        CheckResult(
            "task_geometry",
            improved,
            (
                f"initial={a['initial_dist']:.4f} m -> final={a['final_dist']:.4f} m "
                f"(min={a['min_dist']:.4f} m, success<{SUCCESS_DISTANCE_M} m: {rep.success})"
            ),
        )
    )

    # --- Contacts observable ---
    rep.contact_count_final = a["ncon"]
    rep.checks.append(CheckResult("contacts", True, f"ncon at end of rollout = {a['ncon']}"))

    # --- Optional rendering ---
    if render:
        try:
            mujoco.mj_forward(model, mujoco.MjData(model))
            data = mujoco.MjData(model)
            mujoco.mj_forward(model, data)
            renderer = mujoco.Renderer(model, height=96, width=96)
            renderer.update_scene(data)
            img = renderer.render()
            rep.render_ok = True
            rep.render_mean_pixel = float(img.mean())
            rep.render_detail = f"frame {img.shape} dtype={img.dtype}, mean={img.mean():.2f}"
            renderer.close()
        except Exception as exc:  # pragma: no cover - environment dependent
            rep.render_ok = False
            rep.render_detail = (
                f"SKIPPED (soft): {type(exc).__name__}: {exc}. "
                "Set MUJOCO_GL=glfw|egl|osmesa or install OSMesa for frame capture."
            )

    # Hard requirements only.
    hard = {"import_mujoco", "parse_mjcf", "determinism", "finite_state", "task_geometry"}
    rep.ok = all(c.passed for c in rep.checks if c.name in hard)
    return rep


def _print_human(rep: SmokeReport) -> None:
    print("=" * 68)
    print("SimEval simulator smoke test (Milestone 1)")
    print("=" * 68)
    print(f"python         : {rep.python}")
    print(f"platform       : {rep.platform}")
    print(f"mujoco         : {rep.mujoco_version}")
    print(f"mjcf sha256/16 : {rep.mjcf_hash}")
    print(f"model          : nq={rep.nq} nu={rep.nu} nbody={rep.nbody} ngeom={rep.ngeom}")
    print(f"rollout        : {rep.steps} steps, seed={rep.seed}")
    print("-" * 68)
    for c in rep.checks:
        mark = "PASS" if c.passed else "FAIL"
        print(f"[{mark}] {c.name:<16} {c.detail}")
    if rep.render_requested:
        mark = "PASS" if rep.render_ok else "SOFT"
        print(f"[{mark}] {'render':<16} {rep.render_detail}")
    print("-" * 68)
    print(f"final EE-target distance : {rep.final_ee_target_distance_m:.4f} m")
    print(f"min   EE-target distance : {rep.min_ee_target_distance_m:.4f} m")
    print(f"success (preliminary)    : {rep.success}")
    print(f"contacts (end of rollout): {rep.contact_count_final}")
    print("=" * 68)
    print("SMOKE TEST:", "OK" if rep.ok else "FAILED")
    print("=" * 68)


def main() -> int:
    parser = argparse.ArgumentParser(description="SimEval headless MuJoCo smoke test")
    parser.add_argument("--render", action="store_true", help="also attempt offscreen rendering")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    rep = run(render=args.render)
    if args.json:
        payload = asdict(rep)
        payload["checks"] = [asdict(c) for c in rep.checks]
        print(json.dumps(payload, indent=2))
    else:
        _print_human(rep)
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
