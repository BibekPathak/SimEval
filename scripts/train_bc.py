#!/usr/bin/env python3
"""Train the behavior-cloning policy (Milestone 8).

Two modes:

* ``--mode bc``    — plain behavior cloning: single-pass expert demonstrations.
* ``--mode dagger`` (default) — DAgger: iteratively roll a mixture of the expert
  and the current learner, label visited states with the expert, and retrain.
  DAgger addresses the compounding-error failure that plain BC exhibits here.

The script also runs a quick held-out sanity evaluation for the just-trained
policy so the operator sees whether training actually produced a usable policy.

Pipeline:
  1. Generate a scenario suite (deterministic from ``--base-seed``).
  2. Collect demonstrations / run DAgger over dev+validation scenarios.
  3. Train a compact NumPy MLP (train/validation split, early stopping).
  4. Sanity-evaluate on a *separate* held-out suite.
  5. Persist the dataset (manifest + checksum) and the model checkpoint.

Usage:
    python scripts/train_bc.py
    python scripts/train_bc.py --mode bc --epochs 200
    python scripts/train_bc.py --iterations 5 --epochs 150
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from simulation.datasets.bc_dataset import (
    DATASET_SCHEMA_VERSION,
    FEATURE_NAMES,
    LABEL_NAMES,
    DatasetManifest,
    generate_dataset,
    save_dataset,
)
from simulation.learning.dagger import DaggerConfig, train_dagger
from simulation.learning.mlp import TrainConfig, load_checkpoint, save_checkpoint
from simulation.scenarios.generator import generate_suite


def _sanity_eval(checkpoint_path: str, n_scenarios: int, base_seed: int) -> dict:
    """Evaluate the trained checkpoint on a fresh held-out suite."""
    import tempfile

    from simulation.artifacts.store import LocalArtifactStore
    from simulation.metrics.reach_metrics import compute_metrics
    from simulation.runners.episode_runner import EpisodeConfig, run_episode

    eval_suite = generate_suite(
        suite_name="bc-sanity", suite_version="v1", n_scenarios=n_scenarios, base_seed=base_seed
    )
    with tempfile.TemporaryDirectory() as tmp:
        store = LocalArtifactStore(tmp)
        episodes = [
            run_episode(
                scenario=sc,
                policy_name="behavior_cloning",
                config=EpisodeConfig(
                    capture_every=10,
                    persist_artifacts=False,
                    policy_config={"checkpoint": checkpoint_path},
                ),
                store=store,
                experiment_id="bc-sanity",
            )
            for sc in eval_suite.by_split("held_out")
        ]
    metrics = compute_metrics(episodes, timestep_s=0.005)
    return {
        "n": metrics.n_episodes_evaluated,
        "success": metrics.n_success,
        "success_rate": metrics.success_rate,
        "suite_hash": eval_suite.content_hash(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the SimEval behavior-cloning policy")
    parser.add_argument("--mode", choices=["bc", "dagger"], default="dagger")
    parser.add_argument("--suite-name", default="bc-suite")
    parser.add_argument("--suite-version", default="v1")
    parser.add_argument("--n-scenarios", type=int, default=60)
    parser.add_argument("--base-seed", type=int, default=7000)
    parser.add_argument("--expert", default="ik_planner_baseline")
    parser.add_argument("--control-stride", type=int, default=2)
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--hidden", default="64,64")
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--dataset-dir", default="datasets/bc_reach_v1")
    parser.add_argument("--checkpoint", default="checkpoints/bc_reach_v1.json")
    parser.add_argument("--sanity-n", type=int, default=40, help="held-out sanity scenarios")
    parser.add_argument("--sanity-seed", type=int, default=9000)
    parser.add_argument("--no-sanity", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    suite = generate_suite(
        suite_name=args.suite_name,
        suite_version=args.suite_version,
        n_scenarios=args.n_scenarios,
        base_seed=args.base_seed,
    )
    hidden = tuple(int(h) for h in args.hidden.split(",") if h.strip())

    t0 = time.perf_counter()
    if args.mode == "bc":
        parts_x, parts_y = [], []
        for split in ("dev", "validation"):
            try:
                part = generate_dataset(
                    suite,
                    split=split,
                    expert_policy=args.expert,
                    control_stride=args.control_stride,
                )
            except ValueError:
                continue
            parts_x.append(part["features"])
            parts_y.append(part["labels"])
        features = np.concatenate(parts_x, axis=0)
        labels = np.concatenate(parts_y, axis=0)
        config = TrainConfig(
            hidden_sizes=hidden,
            learning_rate=args.learning_rate,
            epochs=args.epochs,
            seed=args.seed,
        )
        from simulation.learning.mlp import train_mlp

        checkpoint, history = train_mlp(features, labels, config)
        train_report = {
            "mode": "bc",
            "iterations": 1,
            "total_samples": int(features.shape[0]),
            "per_iteration": [
                {
                    "iteration": 0,
                    "beta": 1.0,
                    "samples": int(features.shape[0]),
                    "best_val_loss_normalized": history.best_val_loss,
                    "best_epoch": history.best_epoch,
                }
            ],
        }
    else:
        dagger = DaggerConfig(
            iterations=args.iterations,
            train=TrainConfig(
                hidden_sizes=hidden,
                learning_rate=args.learning_rate,
                epochs=args.epochs,
                seed=args.seed,
            ),
            seed=args.seed,
            control_stride=args.control_stride,
        )
        checkpoint, report = train_dagger(suite, expert_policy=args.expert, config=dagger)
        train_report = {
            "mode": "dagger",
            "iterations": report.iterations,
            "total_samples": report.total_samples,
            "per_iteration": report.per_iteration,
        }
    train_s = time.perf_counter() - t0

    # Persist dataset. For DAgger we store the final aggregated set by
    # regenerating a compact BC dataset for the manifest provenance; the
    # aggregated DAgger samples are the training artefact and are large.
    manifest = DatasetManifest(
        schema_version=DATASET_SCHEMA_VERSION,
        expert_policy=args.expert,
        expert_version="v1",
        task_name=suite.task_name,
        task_version=suite.task_version,
        suite_name=suite.suite_name,
        suite_version=suite.suite_version,
        suite_hash=suite.content_hash(),
        split="dev+validation",
        base_seed=args.base_seed,
        control_stride=args.control_stride,
        n_episodes=len(suite.scenarios),
        n_samples=int(train_report["total_samples"]),
        feature_names=list(FEATURE_NAMES),
        label_names=list(LABEL_NAMES),
        checksum_sha256="",
        extra={
            "mode": train_report["mode"],
            "iterations": train_report["iterations"],
            "per_iteration": train_report["per_iteration"],
        },
    )
    # Store the expert demonstration set as the inspectable dataset artefact.
    demo = generate_dataset(
        suite, split="dev", expert_policy=args.expert, control_stride=args.control_stride
    )
    manifest_path = save_dataset(demo, directory=args.dataset_dir, manifest=manifest)
    checkpoint_path = save_checkpoint(checkpoint, args.checkpoint)

    report: dict = {
        "mode": train_report["mode"],
        "iterations": train_report["iterations"],
        "total_samples": train_report["total_samples"],
        "per_iteration": train_report["per_iteration"],
        "dataset_manifest": str(manifest_path),
        "dataset_checksum": manifest.checksum_sha256,
        "checkpoint": str(checkpoint_path),
        "training_seconds": train_s,
        "suite_hash": suite.content_hash(),
    }

    if not args.no_sanity:
        try:
            load_checkpoint(checkpoint_path)
            report["sanity"] = _sanity_eval(checkpoint_path, args.sanity_n, args.sanity_seed)
        except Exception as exc:
            report["sanity"] = {"error": f"{type(exc).__name__}: {exc}"}

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    print("=" * 68)
    print(f"SimEval behavior-cloning training (mode={report['mode']})")
    print("=" * 68)
    print(
        f"suite              : {suite.suite_name} {suite.suite_version} hash={suite.content_hash()}"
    )
    print(f"expert imitated    : {args.expert}")
    print(f"iterations         : {report['iterations']}")
    print(f"total samples      : {report['total_samples']}")
    for it in report["per_iteration"]:
        print(
            f"  iter {it['iteration']}: beta={it['beta']:<4} samples={it['samples']:<6} "
            f"best_val_loss={it['best_val_loss_normalized']:.5f} (epoch {it['best_epoch']})"
        )
    print(f"dataset            : {report['dataset_manifest']}")
    print(f"checkpoint         : {report['checkpoint']}")
    print(f"training           : {report['training_seconds']:.2f} s")
    sanity = report.get("sanity")
    if sanity and "error" not in sanity:
        print(
            f"sanity (held-out)  : {sanity['success']}/{sanity['n']} "
            f"({(sanity['success_rate'] or 0) * 100:.1f}%)"
        )
    elif sanity:
        print(f"sanity (held-out)  : error: {sanity['error']}")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
