"""Metric computation for evaluated episodes.

Every metric is defined below with units, aggregation method, and limitations.
Metrics operate on :class:`~simulation.runners.outcome.EpisodeResult` records so
that they are computed from persisted evidence, not from live simulator state.

Metric definitions
------------------
success_rate
    Fraction of *evaluated* episodes whose outcome is ``SUCCESS``.
    Units: dimensionless ratio in [0, 1]. Aggregation: mean over episodes.
    Reported with an explicit numerator and denominator. Infrastructure
    failures are excluded from the denominator by default (see
    ``include_infrastructure``), because they are not evidence about the policy.
    Limitation: treats each episode as an independent Bernoulli trial; episodes
    sharing a scenario are correlated, so this is only appropriate at the
    scenario level for inference (handled in the statistics milestone).

completion_time_s
    Simulated duration of a *successful* episode: steps * timestep.
    Units: seconds of simulated time. Aggregation: arithmetic mean / median over
    successful episodes. Limitation: not defined for failed episodes; a failed
    episode contributes no completion time and must not be counted as 0.

episode_length_steps
    Number of control steps executed. Units: steps. Aggregation: mean over all
    evaluated episodes. Limitation: a timeout episode has length == max_steps by
    construction.

collision_rate
    Fraction of episodes with at least one recorded EE-floor contact step.
    Units: ratio. Aggregation: mean over episodes. Limitation: "collision" here
    means EE-floor contact, which is exact for this model because only the end
    effector and floor are collidable. It is *not* a general collision count for
    arbitrary scenes.

mean_collision_steps
    Average number of steps with at least one EE-floor contact. Units: steps.

failure_rate
    Fraction of evaluated episodes whose outcome is not SUCCESS. Units: ratio.
    Equals ``1 - success_rate`` over the same denominator.

failure_categories
    Counts of episodes per failure category. Units: episode counts. Limitation:
    only categories that occurred are reported.

return_mean / return_median
    Mean / median episodic return (sum of rewards) over evaluated episodes.
    Units: reward units. This task uses a sparse terminal reward of 1.0, so
    return is 1.0 for success and 0.0 otherwise; the metric is still computed
    generically from recorded rewards.

throughput_eps_per_s
    Evaluated episodes divided by total wall-clock execution time. Units:
    episodes per second. Limitation: includes episode overhead and is sensitive
    to machine load; it is a throughput figure, not a latency guarantee.

mean_wall_clock_s, mean_policy_inference_ms
    Per-episode wall-clock duration and mean policy inference latency. Units:
    seconds, milliseconds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from simulation.runners.outcome import EpisodeResult, is_infrastructure_failure


@dataclass
class MetricSet:
    """Aggregated metrics over a collection of episodes."""

    n_episodes_total: int = 0
    n_episodes_evaluated: int = 0
    n_infrastructure_failures: int = 0
    n_success: int = 0
    success_rate: float | None = None
    failure_rate: float | None = None
    completion_time_mean_s: float | None = None
    completion_time_median_s: float | None = None
    episode_length_mean_steps: float | None = None
    collision_rate: float | None = None
    mean_collision_steps: float | None = None
    return_mean: float | None = None
    return_median: float | None = None
    throughput_eps_per_s: float | None = None
    mean_wall_clock_s: float | None = None
    mean_policy_inference_ms: float | None = None
    failure_categories: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        import dataclasses

        return dataclasses.asdict(self)


def _finite(values: list[float]) -> list[float]:
    return [v for v in values if v is not None and math.isfinite(v)]


def compute_metrics(
    episodes: list[EpisodeResult],
    *,
    timestep_s: float,
    include_infrastructure: bool = False,
) -> MetricSet:
    """Compute the aggregate metric set over ``episodes``.

    Args:
        episodes: Persisted episode results.
        timestep_s: Simulation timestep, used to convert steps to sim time.
        include_infrastructure: When False (default), episodes whose outcome is
            an infrastructure failure are excluded from rate denominators. They
            are always reported separately in ``n_infrastructure_failures``.
    """
    result = MetricSet(n_episodes_total=len(episodes))

    infra = [e for e in episodes if is_infrastructure_failure(_outcome_of(e))]
    result.n_infrastructure_failures = len(infra)

    if include_infrastructure:
        evaluated = list(episodes)
    else:
        evaluated = [e for e in episodes if not is_infrastructure_failure(_outcome_of(e))]

    result.n_episodes_evaluated = len(evaluated)
    if not evaluated:
        return result

    n = len(evaluated)
    successes = [e for e in evaluated if e.success]
    result.n_success = len(successes)
    result.success_rate = result.n_success / n
    result.failure_rate = 1.0 - result.success_rate

    # Completion time: successful episodes only.
    completion = _finite([e.steps * timestep_s for e in successes])
    if completion:
        result.completion_time_mean_s = float(np.mean(completion))
        result.completion_time_median_s = float(np.median(completion))

    # Episode length: all evaluated episodes.
    lengths = _finite([float(e.steps) for e in evaluated])
    if lengths:
        result.episode_length_mean_steps = float(np.mean(lengths))

    # Collisions.
    collided = [e for e in evaluated if e.collision_steps > 0]
    result.collision_rate = len(collided) / n
    coll_steps = _finite([float(e.collision_steps) for e in evaluated])
    if coll_steps:
        result.mean_collision_steps = float(np.mean(coll_steps))

    # Return.
    returns = _finite([float(e.return_sum) for e in evaluated])
    if returns:
        result.return_mean = float(np.mean(returns))
        result.return_median = float(np.median(returns))

    # Timing.
    walls = _finite([float(e.wall_clock_s) for e in evaluated])
    if walls:
        result.mean_wall_clock_s = float(np.mean(walls))
        total_wall = float(np.sum(walls))
        if total_wall > 0:
            result.throughput_eps_per_s = n / total_wall

    infer_ms = _finite([float(e.policy_inference_s) * 1000.0 for e in evaluated])
    if infer_ms:
        result.mean_policy_inference_ms = float(np.mean(infer_ms))

    # Failure categories.
    categories: dict[str, int] = {}
    for e in evaluated:
        if not e.success and e.failure_category:
            categories[e.failure_category] = categories.get(e.failure_category, 0) + 1
    result.failure_categories = categories

    return result


def _outcome_of(episode: EpisodeResult):
    from simulation.runners.outcome import Outcome

    try:
        return Outcome(episode.outcome)
    except ValueError:
        return Outcome.OTHER_FAILURE


__all__ = ["MetricSet", "compute_metrics"]
