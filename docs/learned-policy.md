# Learned Policy (Milestone 8)

This document describes the optional learned-policy extension: a
**behavior-cloning policy trained with DAgger** on demonstrations from the
classical expert.

## What this is — and is not

* It **is** a genuine learned policy: actions come from a trained neural network,
  and it is evaluated on held-out scenarios and compared with the expert it
  imitates.
* It **is not** end-to-end vision-based manipulation. It consumes low-dimensional
  state (joint positions/velocities and the end-effector-to-target vector), not
  images. There is no perception module, so no perception-to-action claim is made.
* It **is not** a large-scale imitation-learning result. The dataset is small
  (thousands of samples) and task-specific, and it does not generalise beyond the
  reach task.

## Why NumPy rather than a deep-learning framework

The network is a compact MLP (12 → 64 → 64 → 4). A self-contained NumPy
implementation keeps the repository dependency-light, fully deterministic under a
fixed seed, and auditable. This is a deliberate tradeoff: the training loop is
real (forward pass, backpropagation, Adam, train/validation split, early
stopping), but it is not a general-purpose deep-learning stack.

## Pipeline

```
scripts/train_bc.py
  1. generate_suite(base_seed)                 -> versioned scenarios
  2. collect demonstrations / run DAgger       -> (features, expert labels)
  3. train_mlp(features, labels)               -> checkpoint JSON
  4. sanity-evaluate on a held-out suite       -> success rate
  5. save dataset manifest (checksum) + checkpoint

scripts/eval_bc.py
  evaluate expert vs learned on the held-out split
  + one ablation (joint-limit clamping on/off)
  + record failure cases
```

Artifacts are regenerable and therefore git-ignored:
`datasets/bc_reach_v1/` (features/labels + manifest) and
`checkpoints/bc_reach_v1.json` (weights + standardisation + history).

## The central result: plain BC fails, DAgger fixes it

Single-step behavior cloning over 400-step episodes suffers **compounding
error**: the policy is trained only on expert-visited states, drifts off that
distribution, and never learned to recover.

Measured on SimEval (held-out split through the real episode runner):

| Method | Held-out success | Notes |
|--------|-----------------:|-------|
| Expert (`ik_planner_baseline`) | 28/31 (90.3%) | reference controller |
| Plain behavior cloning (BC) | 0/16 (0.0%) | low supervised loss but total failure |
| **DAgger (BC + aggregation)** | **26/31 (83.9%)** | recovers most of the gap |

The plain-BC number is not hidden: it is the motivation for DAgger and is
recorded in `docs/research-log.md`.

DAgger iterates: roll a β-mixture of expert and learner, label every visited
state with the expert action, aggregate, retrain. β decays from 1.0 to 0.5 so
later iterations emphasise learner-visited states.

## Ablation

`scripts/eval_bc.py` also evaluates the learned policy with joint-limit clamping
**disabled**. On the held-out split the two are identical (26/31): after DAgger
the network rarely saturates the limits, so clamping is not load-bearing here.
This is reported as a negative result rather than presented as an improvement.

## Reproducing

```bash
make train-bc        # DAgger training (writes dataset + checkpoint)
make eval-bc         # held-out evaluation + ablation
# or directly:
.venv/bin/python scripts/train_bc.py --mode dagger --iterations 6 --epochs 250
.venv/bin/python scripts/eval_bc.py --n 120
```

Training is deterministic for a fixed `--seed` on a fixed machine.

## Failure analysis

The learned policy's remaining held-out failures are all `TIMEOUT` on hard
scenarios near the workspace boundary (closest approach 0.07–0.20 m versus the
0.05 m threshold). It is slower than the expert (mean ~141 vs ~80 steps) because
DAgger's mixture rollouts spend more time recovering; it reaches the target but
takes longer to satisfy the success dwell.

## Limitations

* Single task, single expert, low-dimensional state — no images, no VLA.
* Not a training-ready dataset claim; the manifest exists so the data is
  inspectable and reproducible, not because it is suitable for other models.
* Held-out success is measured on 31 scenarios; the interval is wide, so treat
  the 90.3% vs 83.9% gap as indicative rather than precise (see
  `docs/evaluation-methodology.md`).
* Cross-machine determinism of training is not guaranteed (BLAS ordering).
