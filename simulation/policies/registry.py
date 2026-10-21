"""Policy registry and construction helpers.

Policies are constructed from a serializable configuration plus a kinematics
context. The registry lets the API and experiment layer build policies by name
without importing concrete classes everywhere.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from simulation.policies.base import Policy, PolicyConfig
from simulation.policies.behavior_cloning import BehaviorCloningConfig, BehaviorCloningPolicy
from simulation.policies.context import KinematicsContext
from simulation.policies.ik_planner import IKPlannerConfig, IKPlannerPolicy
from simulation.policies.resolved_rate import ResolvedRateConfig, ResolvedRatePolicy

PolicyFactory = Callable[[PolicyConfig, KinematicsContext], Policy]


def _make_ik_planner(config: PolicyConfig, ctx: KinematicsContext) -> Policy:
    if not isinstance(config, IKPlannerConfig):
        config = IKPlannerConfig(**{**config.to_dict()})
    return IKPlannerPolicy(config, ctx)


def _make_resolved_rate(config: PolicyConfig, ctx: KinematicsContext) -> Policy:
    if not isinstance(config, ResolvedRateConfig):
        config = ResolvedRateConfig(**{**config.to_dict()})
    return ResolvedRatePolicy(config, ctx)


def _make_behavior_cloning(config: PolicyConfig, ctx: KinematicsContext) -> Policy:
    if not isinstance(config, BehaviorCloningConfig):
        config = BehaviorCloningConfig(**{**config.to_dict()})
    return BehaviorCloningPolicy(config, ctx)


_REGISTRY: dict[str, tuple[type[PolicyConfig], PolicyFactory, str]] = {
    "ik_planner_baseline": (IKPlannerConfig, _make_ik_planner, "Baseline full-IK setpoint planner"),
    "resolved_rate_candidate": (
        ResolvedRateConfig,
        _make_resolved_rate,
        "Candidate incremental resolved-rate controller",
    ),
    "behavior_cloning": (
        BehaviorCloningConfig,
        _make_behavior_cloning,
        "Learned behavior-cloning policy (imitation of the baseline expert)",
    ),
}


def available_policies() -> list[dict[str, Any]]:
    """Describe registered policies for API/listing purposes."""
    out = []
    for name, (config_cls, _factory, description) in _REGISTRY.items():
        defaults = config_cls()
        out.append(
            {
                "name": name,
                "version": defaults.version,
                "description": description,
                "default_config": defaults.to_dict(),
            }
        )
    return out


def build_policy(
    name: str,
    config: dict[str, Any] | None,
    context: KinematicsContext,
) -> Policy:
    """Construct a policy by registered name from a config mapping."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown policy '{name}'. Available: {sorted(_REGISTRY)}")
    config_cls, factory, _desc = _REGISTRY[name]
    merged = {**config_cls().to_dict(), **(config or {})}
    cfg = config_cls(**merged)
    return factory(cfg, context)


# Backwards-friendly aliases used across docs/tests.
BASELINE_POLICY_NAME = "ik_planner_baseline"
CANDIDATE_POLICY_NAME = "resolved_rate_candidate"

__all__ = [
    "BASELINE_POLICY_NAME",
    "CANDIDATE_POLICY_NAME",
    "available_policies",
    "build_policy",
]
