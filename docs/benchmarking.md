# Benchmarking

> Numbers below are **measured on the development machine**, not claims.
> They are single-process, single-threaded, CPU-only. Re-run
> `python scripts/benchmark.py` to reproduce them on your hardware.

## Method

- **Harness:** `scripts/benchmark.py`, one warm-up episode then a timed
  batch through the real `run_episode` pipeline (simulation + policy
  inference + trace recording + grading + artifact serialisation).
- **Timing:** wall-clock via `time.perf_counter`.
- **Workload:** 40 scenarios from a seeded suite, policy
  `ik_planner_baseline`, `capture_every=1`, task reach v1,
  max 400 steps at 0.005 s/step.
- **Unit:** the episode. Throughput counts completed, graded episodes.
- **Excluded:** process start-up, database persistence (measured separately
  below is storage serialisation only), and rendering (off by default).

## Environment

- Platform: Linux 7.1.9-hardened1-1-hardened (x86_64), 12 CPUs
- Python 3.12.7, NumPy 2.5.4, MuJoCo 3.16.0
- No GPU; evaluation is headless.

## Results

| Metric | Value |
|--------|-------|
| Episodes evaluated | 40 |
| Total wall clock | 4.582 s |
| **Episodes / second** | **8.731** |
| Mean episode wall clock | 0.1145 s |
| Total simulated time | 17.430 s |
| Real-time factor (sim / wall) | 3.8× |
| Control steps / second | 761 |
| Policy inference (mean) | 98.90 ms/episode |
| Sim + overhead total | 0.626 s |
| Artifact serialize (400×11 array batch) | 2.112 ms (34679 bytes on disk) |
| Success rate (this sample) | 87.5% (35/40) |

## Interpretation and limitations

- Throughput and latency are indicative and machine-load sensitive; they
  are **not** performance guarantees.
- The reach task is lightweight; these figures do not extrapolate to
  contact-rich or rendering-heavy tasks.
- Policy inference dominates wall clock for the baseline IK planner, which
  solves inverse kinematics every step; a cheaper policy increases
  throughput.
- Database persistence is measured in the backend tests, not here.
