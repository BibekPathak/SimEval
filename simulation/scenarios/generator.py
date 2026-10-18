"""Versioned, seeded scenario generation for the reach task.

A scenario fully specifies the initial conditions for one episode:

* a deterministic ``seed`` (drives initial joint noise and any scenario-level
  randomness),
* the target pose the end effector must reach,
* an initial joint configuration (or ``None`` for the model default),
* the initial joint-noise magnitude,
* a difficulty tier and a scenario split.

Scenarios are grouped into a :class:`ScenarioSuite` with a version string. The
suite is the unit recorded by experiments so that comparisons always reference
an identical, reproducible scenario set.

Split discipline
----------------
``dev`` and ``validation`` scenarios are for iteration and policy selection.
``held_out`` scenarios must not be used to tune a policy; the generator assigns
splits by seed so that the same logical scenario never appears in more than one
split. ``assert_no_leakage`` verifies this property.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import numpy as np

Split = Literal["dev", "validation", "held_out"]
DifficultyTier = Literal["easy", "medium", "hard"]

#: Reachable workspace shell for the arm, determined empirically. Targets are
#: sampled in this spherical shell so that they are physically reachable with
#: some margin while still varying in difficulty.
_REACH_RADIUS_MIN = 0.18
_REACH_RADIUS_MAX = 0.40
_REACH_Z_MIN = 0.20
_REACH_Z_MAX = 0.62


@dataclass(frozen=True)
class Scenario:
    """A single fully-specified evaluation scenario."""

    scenario_id: str
    task_name: str
    task_version: str
    seed: int
    target_position: list[float]
    initial_qpos: list[float] | None
    qpos_noise: float
    difficulty: DifficultyTier
    split: Split
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def content_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


#: Joint limits of the reach arm, mirrored from the MJCF. Used to sample
#: adversarial initial postures without a MuJoCo dependency in this module.
_JOINT_LIMITS: list[tuple[float, float]] = [
    (-3.14, 3.14),
    (-1.6, 1.6),
    (-1.6, 1.6),
    (-1.6, 1.6),
]


@dataclass(frozen=True)
class ScenarioSuite:
    """A versioned, named collection of scenarios."""

    suite_name: str
    suite_version: str
    task_name: str
    task_version: str
    scenarios: list[Scenario]
    generator: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "suite_version": self.suite_version,
            "task_name": self.task_name,
            "task_version": self.task_version,
            "generator": self.generator,
            "scenarios": [s.to_dict() for s in self.scenarios],
        }

    def content_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:16]

    def by_split(self, split: Split) -> list[Scenario]:
        return [s for s in self.scenarios if s.split == split]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.scenarios:
            out[s.split] = out.get(s.split, 0) + 1
        return out

    def get(self, scenario_id: str) -> Scenario:
        for s in self.scenarios:
            if s.scenario_id == scenario_id:
                return s
        raise KeyError(scenario_id)

    def verify(self) -> None:
        assert_no_leakage(self)


def _sample_target(rng: np.random.Generator, tier: DifficultyTier) -> list[float]:
    """Sample a reachable target pose for a difficulty tier.

    Difficulty is expressed as distance from the workspace centre and the size
    of the hard boundary: easy targets sit near the nominal pose, hard targets
    approach the reach limits and may require yaw.
    """
    if tier == "easy":
        radius = rng.uniform(0.18, 0.26)
        yaw = rng.uniform(-0.4, 0.4)
    elif tier == "medium":
        radius = rng.uniform(0.24, 0.34)
        yaw = rng.uniform(-0.9, 0.9)
    else:  # hard
        radius = rng.uniform(0.32, _REACH_RADIUS_MAX)
        yaw = rng.uniform(-1.4, 1.4)
    z = float(np.clip(rng.uniform(_REACH_Z_MIN, _REACH_Z_MAX), _REACH_Z_MIN, _REACH_Z_MAX))
    return [float(radius * np.cos(yaw)), float(radius * np.sin(yaw)), z]


def _split_for_seed(seed: int, dev_frac: float, val_frac: float) -> Split:
    """Deterministically assign a split from a seed.

    Splitting on the seed (not on the sampled pose) guarantees a logical
    scenario lands in exactly one split.
    """
    u = ((seed * 2654435761) % (2**32)) / float(2**32)
    if u < dev_frac:
        return "dev"
    if u < dev_frac + val_frac:
        return "validation"
    return "held_out"


def _sample_initial_qpos(rng: np.random.Generator, tier: DifficultyTier) -> list[float] | None:
    """Sample an adversarial initial posture for harder tiers.

    Easy scenarios start from the model default (``None``). Medium and hard
    scenarios start from a randomly perturbed posture so the controller must
    recover before reaching the target.
    """
    if tier == "easy":
        return None
    spread = 0.5 if tier == "medium" else 0.9
    q = [
        rng.uniform(max(lo, -spread), min(hi, spread)) if i < 2 else rng.uniform(lo, hi)
        for i, (lo, hi) in enumerate(_JOINT_LIMITS)
    ]
    return [float(x) for x in q]


def generate_suite(
    *,
    suite_name: str = "reach-default",
    suite_version: str = "v1",
    task_name: str = "reach",
    task_version: str = "v1",
    n_scenarios: int = 30,
    base_seed: int = 1000,
    dev_frac: float = 0.5,
    val_frac: float = 0.25,
    difficulty_counts: dict[DifficultyTier, int] | None = None,
    qpos_noise: float = 0.0,
) -> ScenarioSuite:
    """Generate a reproducible scenario suite.

    Args:
        difficulty_counts: Optional explicit count per tier. If omitted, tiers
            are assigned round-robin so all tiers appear.
        qpos_noise: Per-joint initial noise magnitude applied at reset. 0.0
            keeps resets fully deterministic.
    """
    difficulty_counts = difficulty_counts or {}
    tiers: list[DifficultyTier] = ["easy", "medium", "hard"]

    scenarios: list[Scenario] = []
    for i in range(n_scenarios):
        seed = base_seed + i
        rng = np.random.default_rng(seed)
        if difficulty_counts:
            tier: DifficultyTier = list(difficulty_counts.keys())[i % len(difficulty_counts)]
        else:
            tier = tiers[i % len(tiers)]
        target = _sample_target(rng, tier)
        split = _split_for_seed(seed, dev_frac, val_frac)
        scenario = Scenario(
            scenario_id=f"{suite_name}-{suite_version}-{i:04d}",
            task_name=task_name,
            task_version=task_version,
            seed=seed,
            target_position=target,
            initial_qpos=_sample_initial_qpos(rng, tier),
            qpos_noise=qpos_noise,
            difficulty=tier,
            split=split,
            metadata={"tier": tier, "index": i},
        )
        scenarios.append(scenario)

    suite = ScenarioSuite(
        suite_name=suite_name,
        suite_version=suite_version,
        task_name=task_name,
        task_version=task_version,
        scenarios=scenarios,
        generator={
            "n_scenarios": n_scenarios,
            "base_seed": base_seed,
            "dev_frac": dev_frac,
            "val_frac": val_frac,
            "difficulty_counts": difficulty_counts,
            "qpos_noise": qpos_noise,
        },
    )
    suite.verify()
    return suite


def assert_no_leakage(suite: ScenarioSuite) -> None:
    """Raise if the same logical scenario appears in multiple splits."""
    seen: dict[str, Split] = {}
    for s in suite.scenarios:
        key = f"{s.task_name}:{s.task_version}:{s.seed}"
        if key in seen and seen[key] != s.split:
            raise ValueError(
                f"scenario leakage: seed {s.seed} appears in both {seen[key]!r} and {s.split!r}"
            )
        seen[key] = s.split
    ids = [s.scenario_id for s in suite.scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario_id detected in suite")


def load_suite(path: str) -> ScenarioSuite:
    """Load a suite from a JSON file written by ``save_suite``."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    scenarios = [
        Scenario(
            scenario_id=s["scenario_id"],
            task_name=s["task_name"],
            task_version=s["task_version"],
            seed=s["seed"],
            target_position=list(s["target_position"]),
            initial_qpos=s.get("initial_qpos"),
            qpos_noise=s.get("qpos_noise", 0.0),
            difficulty=s["difficulty"],
            split=s["split"],
            metadata=s.get("metadata", {}),
        )
        for s in raw["scenarios"]
    ]
    suite = ScenarioSuite(
        suite_name=raw["suite_name"],
        suite_version=raw["suite_version"],
        task_name=raw["task_name"],
        task_version=raw["task_version"],
        scenarios=scenarios,
        generator=raw.get("generator", {}),
    )
    suite.verify()
    return suite


def save_suite(suite: ScenarioSuite, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(suite.to_dict(), fh, indent=2, sort_keys=True)


__all__ = [
    "DifficultyTier",
    "Scenario",
    "ScenarioSuite",
    "Split",
    "assert_no_leakage",
    "generate_suite",
    "load_suite",
    "save_suite",
]
