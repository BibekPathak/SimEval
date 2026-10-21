"""Minimal NumPy neural-network training for the behavior-cloning policy.

Why NumPy and not a deep-learning framework?
--------------------------------------------
The target is a compact MLP over a 12-dimensional observation. A self-contained
NumPy implementation keeps the repository dependency-light (no multi-gigabyte
framework install), fully deterministic under a fixed seed, and easy to audit.
This is a deliberate, documented tradeoff: the pipeline is real (forward pass,
backpropagation, Adam, train/validation split, early stopping), but it is not a
general-purpose deep-learning stack and does not claim to be.

Everything here is deterministic for a fixed seed on a fixed machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

MODEL_SCHEMA_VERSION = "1"


@dataclass
class TrainConfig:
    hidden_sizes: tuple[int, ...] = (64, 64)
    learning_rate: float = 1e-3
    batch_size: int = 128
    epochs: int = 200
    val_fraction: float = 0.2
    seed: int = 0
    l2: float = 1e-5
    early_stop_patience: int = 20
    feature_mean: list[float] | None = None
    feature_std: list[float] | None = None
    label_mean: list[float] | None = None
    label_std: list[float] | None = None


@dataclass
class TrainHistory:
    train_loss: list[float] = field(default_factory=list)
    val_loss: list[float] = field(default_factory=list)
    best_epoch: int = -1
    best_val_loss: float = float("inf")
    n_train: int = 0
    n_val: int = 0


class _MLP:
    """A small fully-connected network with ReLU hidden layers."""

    def __init__(self, sizes: list[int], rng: np.random.Generator) -> None:
        self.sizes = sizes
        self.params: list[dict[str, np.ndarray]] = []
        for i in range(len(sizes) - 1):
            fan_in = sizes[i]
            # He initialisation for ReLU layers.
            w = rng.normal(0.0, np.sqrt(2.0 / fan_in), size=(fan_in, sizes[i + 1]))
            b = np.zeros(sizes[i + 1])
            self.params.append({"w": w.astype(np.float64), "b": b})

    def forward(self, x: np.ndarray) -> tuple[np.ndarray, list[np.ndarray]]:
        activations = [x]
        a = x
        last = len(self.params) - 1
        for i, layer in enumerate(self.params):
            z = a @ layer["w"] + layer["b"]
            a = np.maximum(z, 0.0) if i < last else z  # ReLU hidden, linear output
            activations.append(a)
        return a, activations

    def backward(
        self, activations: list[np.ndarray], grad_out: np.ndarray, l2: float
    ) -> list[dict[str, np.ndarray]]:
        grads: list[dict[str, np.ndarray]] = [{} for _ in self.params]
        delta = grad_out
        for i in reversed(range(len(self.params))):
            a_prev = activations[i]
            grads[i]["w"] = a_prev.T @ delta + l2 * self.params[i]["w"]
            grads[i]["b"] = delta.sum(axis=0)
            if i > 0:
                delta = (delta @ self.params[i]["w"].T) * (activations[i] > 0.0)
        return grads


def train_mlp(
    features: np.ndarray,
    labels: np.ndarray,
    config: TrainConfig | None = None,
) -> tuple[dict[str, Any], TrainHistory]:
    """Train an MLP by behavior cloning. Returns (checkpoint_dict, history).

    Standardisation statistics are computed on the training split only and
    stored in the checkpoint so inference applies the identical transform.
    """
    config = config or TrainConfig()
    rng = np.random.default_rng(config.seed)

    x = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    n = x.shape[0]
    if n < 4:
        raise ValueError(f"need at least 4 samples to train, got {n}")

    perm = rng.permutation(n)
    n_val = max(1, round(n * config.val_fraction))
    val_idx, train_idx = perm[:n_val], perm[n_val:]
    x_train, y_train = x[train_idx], y[train_idx]
    x_val, y_val = x[val_idx], y[val_idx]

    feature_mean = x_train.mean(axis=0)
    feature_std = x_train.std(axis=0)
    feature_std[feature_std < 1e-8] = 1.0
    label_mean = y_train.mean(axis=0)
    label_std = y_train.std(axis=0)
    label_std[label_std < 1e-8] = 1.0

    xn = (x_train - feature_mean) / feature_std
    yn = (y_train - label_mean) / label_std
    xv = (x_val - feature_mean) / feature_std
    yv = (y_val - label_mean) / label_std

    sizes = [x.shape[1], *config.hidden_sizes, y.shape[1]]
    net = _MLP(sizes, rng)

    # Adam state.
    m = [{"w": np.zeros_like(p["w"]), "b": np.zeros_like(p["b"])} for p in net.params]
    v = [{"w": np.zeros_like(p["w"]), "b": np.zeros_like(p["b"])} for p in net.params]
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    step = 0

    history = TrainHistory(n_train=x_train.shape[0], n_val=x_val.shape[0])
    best_params: list[dict[str, np.ndarray]] | None = None
    epochs_without_improvement = 0

    for epoch in range(config.epochs):
        order = rng.permutation(x_train.shape[0])
        for start in range(0, len(order), config.batch_size):
            batch = order[start : start + config.batch_size]
            xb, yb = xn[batch], yn[batch]
            pred, acts = net.forward(xb)
            grad_out = (2.0 / xb.shape[0]) * (pred - yb)
            grads = net.backward(acts, grad_out, config.l2)
            step += 1
            for i in range(len(net.params)):
                for key in ("w", "b"):
                    g = grads[i][key]
                    m[i][key] = beta1 * m[i][key] + (1 - beta1) * g
                    v[i][key] = beta2 * v[i][key] + (1 - beta2) * (g * g)
                    m_hat = m[i][key] / (1 - beta1**step)
                    v_hat = v[i][key] / (1 - beta2**step)
                    net.params[i][key] -= config.learning_rate * m_hat / (np.sqrt(v_hat) + eps)

        train_pred, _ = net.forward(xn)
        train_loss = float(np.mean((train_pred - yn) ** 2))
        val_pred, _ = net.forward(xv)
        val_loss = float(np.mean((val_pred - yv) ** 2))
        history.train_loss.append(train_loss)
        history.val_loss.append(val_loss)

        if val_loss < history.best_val_loss - 1e-9:
            history.best_val_loss = val_loss
            history.best_epoch = epoch
            best_params = [{"w": p["w"].copy(), "b": p["b"].copy()} for p in net.params]
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= config.early_stop_patience:
                break

    if best_params is not None:
        net.params = best_params

    checkpoint: dict[str, Any] = {
        "schema_version": MODEL_SCHEMA_VERSION,
        "input_dim": int(sizes[0]),
        "output_dim": int(sizes[-1]),
        "hidden_sizes": list(config.hidden_sizes),
        "feature_mean": feature_mean.tolist(),
        "feature_std": feature_std.tolist(),
        "label_mean": label_mean.tolist(),
        "label_std": label_std.tolist(),
        "params": [{"w": p["w"].tolist(), "b": p["b"].tolist()} for p in net.params],
        "train_config": {
            "learning_rate": config.learning_rate,
            "batch_size": config.batch_size,
            "epochs": config.epochs,
            "val_fraction": config.val_fraction,
            "seed": config.seed,
            "l2": config.l2,
        },
        "history": {
            "best_epoch": history.best_epoch,
            "best_val_loss": history.best_val_loss,
            "n_train": history.n_train,
            "n_val": history.n_val,
            "final_train_loss": history.train_loss[-1] if history.train_loss else None,
        },
    }
    return checkpoint, history


def save_checkpoint(checkpoint: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
    return path


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != MODEL_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported checkpoint schema {data.get('schema_version')!r}; "
            f"expected {MODEL_SCHEMA_VERSION!r}"
        )
    return data


def predict(checkpoint: dict[str, Any], features: np.ndarray) -> np.ndarray:
    """Deterministic forward pass applying the stored standardisation."""
    x = np.asarray(features, dtype=np.float64)
    mean = np.asarray(checkpoint["feature_mean"])
    std = np.asarray(checkpoint["feature_std"])
    l_mean = np.asarray(checkpoint["label_mean"])
    l_std = np.asarray(checkpoint["label_std"])
    xn = (x - mean) / std
    a = xn
    params = checkpoint["params"]
    for i, layer in enumerate(params):
        w = np.asarray(layer["w"])
        b = np.asarray(layer["b"])
        a = a @ w + b
        if i < len(params) - 1:
            a = np.maximum(a, 0.0)
    return a * l_std + l_mean


__all__ = [
    "MODEL_SCHEMA_VERSION",
    "TrainConfig",
    "TrainHistory",
    "load_checkpoint",
    "predict",
    "save_checkpoint",
    "train_mlp",
]
