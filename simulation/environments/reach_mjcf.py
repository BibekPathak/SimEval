"""MJCF model definition for the SimEval reach task.

Model provenance
----------------
This MJCF is authored specifically for SimEval and is released under the same
Apache-2.0 license as the rest of the repository. It contains no third-party
geometry, meshes, or assets, so it can be redistributed and reproduced freely.

Geometry summary
----------------
A planar 4-DOF revolute arm (base yaw + shoulder + elbow + wrist pitch) mounted
at the origin. The end effector carries a collidable sphere and the ``ee_site``.
A non-colliding spherical goal marker defines the ``target_site``. The target
pose is set programmatically per scenario by writing ``model.body_pos`` for the
``target`` body.

Collision policy
----------------
Arm link geoms use ``contype=0 conaffinity=0`` so the kinematic chain does not
self-collide or collide with the floor. This is a deliberate modeling choice for
a kinematic reach task: self-collision at the base previously injected spurious
joint drift. The end-effector sphere remains collidable so that contact metrics
(e.g. accidental floor contact) are meaningful. This policy is documented here
because it directly affects the interpretation of contact metrics.
"""

from __future__ import annotations

# The target body is repositioned per scenario; the value below is the default
# nominal pose and is overwritten by the scenario's target pose.
MJCF_REACH = """
<mujoco model="simeval_reach_v1">
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
      <geom name="base_g" contype="0" conaffinity="0" type="cylinder"
            size="0.05 0.03" pos="0 0 0.03"/>
      <body name="link1" pos="0 0 0.06" gravcomp="1">
        <joint name="j1" type="hinge" axis="0 0 1" range="-3.14 3.14"/>
        <geom name="link1_g" contype="0" conaffinity="0" type="capsule"
              fromto="0 0 0 0 0 0.30" size="0.025"/>
        <body name="link2" pos="0 0 0.30" quat="0.9238795 0 0.3826834 0" gravcomp="1">
          <joint name="j2" type="hinge" axis="0 1 0" range="-1.6 1.6"/>
          <geom name="link2_g" contype="0" conaffinity="0" type="capsule"
                fromto="0 0 0 0 0 0.25" size="0.022"/>
          <body name="link3" pos="0 0 0.25" quat="0.9238795 0 0.3826834 0" gravcomp="1">
            <joint name="j3" type="hinge" axis="0 1 0" range="-1.6 1.6"/>
            <geom name="link3_g" contype="0" conaffinity="0" type="capsule"
                  fromto="0 0 0 0 0 0.20" size="0.02"/>
            <body name="ee" pos="0 0 0.20" gravcomp="1">
              <joint name="j4" type="hinge" axis="0 1 0" range="-1.6 1.6"/>
              <site name="ee_site" pos="0 0 0"/>
              <geom name="ee_g" type="sphere" size="0.03" rgba="0.85 0.35 0.30 1"/>
            </body>
          </body>
        </body>
      </body>
    </body>
    <body name="target" pos="0.25 0 0.55">
      <geom name="target_g" type="sphere" size="0.035" rgba="0.30 0.80 0.40 1"
            contype="0" conaffinity="0"/>
      <site name="target_site" pos="0 0 0"/>
    </body>
  </worldbody>
  <actuator>
    <position name="a1" joint="j1" kp="300" kv="30"/>
    <position name="a2" joint="j2" kp="300" kv="30"/>
    <position name="a3" joint="j3" kp="300" kv="30"/>
    <position name="a4" joint="j4" kp="300" kv="30"/>
  </actuator>
</mujoco>
"""

__all__ = ["MJCF_REACH"]
