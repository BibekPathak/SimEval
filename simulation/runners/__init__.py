"""Episode execution, outcome typing, and trace recording.

``run_episode``/``EpisodeConfig`` are imported lazily by callers
(``from simulation.runners.episode_runner import ...``) so that importing the
lightweight outcome types does not pull in the environment/grader graph and
create an import cycle.
"""

from simulation.runners.outcome import (
    INFRASTRUCTURE_OUTCOMES,
    EpisodeResult,
    Outcome,
    is_infrastructure_failure,
)
from simulation.runners.trace import TraceRecorder

__all__ = [
    "INFRASTRUCTURE_OUTCOMES",
    "EpisodeResult",
    "Outcome",
    "TraceRecorder",
    "is_infrastructure_failure",
]
