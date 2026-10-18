"""Policy interface for SimEval.

A policy maps an observation (and, if needed, additional environment geometry)
to an action vector. Policies must be deterministic when declared so, and must
be constructible purely from a serializable configuration so that experiments
can be reproduced from their saved configuration alone.

The interface is deliberately minimal:

* ``PolicyConfig``      -- frozen, serializable configuration dataclass.
* ``Policy``            -- abstract base with ``act`` and ``reset``.

Concrete policies live alongside this module. Learned policies (imitation,
reinforcement learning, VLA) can implement the same interface later without
changing the runner or evaluation engine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Generic, TypeVar

import numpy as np

ConfigT = TypeVar("ConfigT", bound="PolicyConfig")


@dataclass(frozen=True)
class PolicyConfig:
    """Base class for policy configurations.

    Subclasses add fields. ``to_dict`` produces a JSON-serializable mapping used
    for experiment records and reproduction.
    """

    name: str = "policy"
    version: str = "v0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Policy(ABC, Generic[ConfigT]):
    """Abstract robot policy.

    Attributes:
        name: Human-readable policy family name.
        version: Policy version string. Bump on any behaviour change.
        deterministic: Whether ``act`` is deterministic given its inputs.
    """

    name: ClassVar[str] = "policy"
    version: ClassVar[str] = "v0"
    deterministic: ClassVar[bool] = True

    def __init__(self, config: ConfigT) -> None:
        self.config = config

    @abstractmethod
    def act(self, observation: dict[str, np.ndarray]) -> np.ndarray:
        """Return an action (desired joint positions) for the observation."""

    def reset(self) -> None:
        """Reset any internal state between episodes. Default: no-op."""

    def config_dict(self) -> dict[str, Any]:
        return self.config.to_dict()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{type(self).__name__}({self.config_dict()})"


__all__ = ["Policy", "PolicyConfig"]
