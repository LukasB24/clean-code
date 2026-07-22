"""Hyperband search over learning_rate/RIDGE_PENALTY, then pick CM307's threshold.

Dev-only tooling (numpy only, never installed at runtime). Two stages:

1. Hyperband (Li et al., 2016) samples `(learning_rate, ridge_penalty)` configs
   and allocates training iterations as the scarce resource: cheap, short
   runs eliminate weak configs early so the budget concentrates on promising
   ones, instead of grid search paying the full iteration cost for every
   candidate up front. Ranking is by best-achievable validation F2 (recall
   weighted over precision, across every threshold) — never test, so it
   stays a clean generalization estimate. The winner is refit once at the
   full resource budget `MAX_ITERATIONS`, which becomes the baked `ITERATIONS`.
2. The winning model's threshold is then chosen exactly as before: maximize
   validation recall (ties broken by precision), subject to a precision
   floor and a safety margin over issue #28's two held-out acceptance
   examples, so neither can drift across the decision boundary from minor
   numeric changes.

    PYTHONPATH=src python tools/tune_head.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cleancode.semantics.training as training_module  # noqa: E402
from cleancode.semantics.backbone import load_table  # noqa: E402
from cleancode.semantics.training import fit_logistic_regression, split_dataset  # noqa: E402

DATASET = Path(__file__).parent / "data" / "what_why.jsonl"
ACCEPTANCE_PROCEDURAL_EXAMPLE = "Adds two numbers and returns the sum"
ACCEPTANCE_RATIONALE_EXAMPLE = "to maximize L1 cache hits"

SEARCH_SEED = 0
LEARNING_RATE_RANGE = (1e-3, 5.0)  # log-uniform
RIDGE_PENALTY_RANGE = (1e-5, 1e-1)  # log-uniform
MAX_ITERATIONS = 15000  # Hyperband's resource budget R; also the baked ITERATIONS
ETA = 3  # Hyperband's halving factor

THRESHOLD_CANDIDATES = [round(value, 2) for value in np.arange(0.15, 0.71, 0.05)]
MIN_PRECISION = 0.6  # floor below which a recall gain is not worth the false-positive cost
MIN_ACCEPTANCE_MARGIN = 0.05  # threshold must clear both acceptance examples by at least this much


def load_dataset() -> tuple[np.ndarray, np.ndarray]:
    table = load_table()
    features, labels = [], []
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        embedding = table.embed(record["text"])
        if embedding is None:
            continue
        features.append(embedding)
        labels.append(1 if record["label"] == "what" else 0)
    return np.array(features), np.array(labels)


def scores_for(weights: np.ndarray, bias: float, features: np.ndarray) -> np.ndarray:
    logits = np.clip(features @ weights + bias, -500, 500)
    return 1.0 / (1.0 + np.exp(-logits))


def precision_recall(probabilities: np.ndarray, labels: np.ndarray, threshold: float) -> tuple[float, float]:
    predicted_positive = probabilities >= threshold
    actual_positive = labels == 1
    true_positive = int((predicted_positive & actual_positive).sum())
    predicted_count = int(predicted_positive.sum())
    actual_count = int(actual_positive.sum())
    precision = true_positive / predicted_count if predicted_count else 0.0
    recall = true_positive / actual_count if actual_count else 0.0
    return precision, recall


def best_f2(probabilities: np.ndarray, labels: np.ndarray) -> float:
    """Best F2 achievable over `THRESHOLD_CANDIDATES` — the Hyperband ranking score."""
    best = 0.0
    for threshold in THRESHOLD_CANDIDATES:
        precision, recall = precision_recall(probabilities, labels, threshold)
        denominator = 4 * precision + recall
        f2 = 5 * precision * recall / denominator if denominator else 0.0
        best = max(best, f2)
    return best


class Config:
    def __init__(self, learning_rate: float, ridge_penalty: float) -> None:
        self.learning_rate = learning_rate
        self.ridge_penalty = ridge_penalty

    def __repr__(self) -> str:
        return f"Config(lr={self.learning_rate:.4g}, ridge={self.ridge_penalty:.4g})"


def sample_config(rng: np.random.Generator) -> Config:
    log_lr = rng.uniform(math.log(LEARNING_RATE_RANGE[0]), math.log(LEARNING_RATE_RANGE[1]))
    log_ridge = rng.uniform(math.log(RIDGE_PENALTY_RANGE[0]), math.log(RIDGE_PENALTY_RANGE[1]))
    return Config(learning_rate=math.exp(log_lr), ridge_penalty=math.exp(log_ridge))


def evaluate(
    config: Config,
    iterations: int,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    val_features: np.ndarray,
    val_labels: np.ndarray,
) -> float:
    """Fits `config` for `iterations` steps and returns its validation F2, or -1 if it diverged."""
    training_module.LEARNING_RATE = config.learning_rate
    training_module.RIDGE_PENALTY = config.ridge_penalty
    training_module.ITERATIONS = iterations
    weights, bias = fit_logistic_regression(train_features, train_labels)
    if not (np.all(np.isfinite(weights)) and np.isfinite(bias)):
        return -1.0
    probabilities = scores_for(weights, bias, val_features)
    return best_f2(probabilities, val_labels)


def _run_round(
    configs: list[Config],
    budget: int,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    val_features: np.ndarray,
    val_labels: np.ndarray,
) -> list[tuple[float, Config]]:
    scored = [
        (evaluate(config, budget, train_features, train_labels, val_features, val_labels), config)
        for config in configs
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def _run_bracket(
    s: int,
    num_configs: int,
    min_budget: float,
    rng: np.random.Generator,
    train_features: np.ndarray,
    train_labels: np.ndarray,
    val_features: np.ndarray,
    val_labels: np.ndarray,
) -> tuple[float, Config]:
    configs = [sample_config(rng) for _ in range(num_configs)]
    bracket_best_score, bracket_best_config = -1.0, configs[0]
    for round_index in range(s + 1):
        budget = max(1, int(round(min_budget * ETA**round_index)))
        scored = _run_round(configs, budget, train_features, train_labels, val_features, val_labels)
        if scored[0][0] > bracket_best_score:
            bracket_best_score, bracket_best_config = scored[0]
        survivors = max(1, math.floor(len(configs) / ETA))
        configs = [config for _, config in scored[:survivors]]
    return bracket_best_score, bracket_best_config


def hyperband(
    train_features: np.ndarray,
    train_labels: np.ndarray,
    val_features: np.ndarray,
    val_labels: np.ndarray,
) -> Config:
    rng = np.random.default_rng(SEARCH_SEED)
    s_max = int(math.floor(math.log(MAX_ITERATIONS, ETA)))
    budget_total = (s_max + 1) * MAX_ITERATIONS

    best_config, best_score = None, -1.0
    for s in reversed(range(s_max + 1)):
        num_configs = math.ceil((budget_total / MAX_ITERATIONS / (s + 1)) * ETA**s)
        min_budget = MAX_ITERATIONS * ETA ** (-s)
        score, config = _run_bracket(
            s, num_configs, min_budget, rng, train_features, train_labels, val_features, val_labels
        )
        if score > best_score:
            best_score, best_config = score, config

    assert best_config is not None
    return best_config


def _select_threshold(
    val_probabilities: np.ndarray,
    val_labels: np.ndarray,
    procedural_score: float,
    rationale_score: float,
) -> tuple[float, float, float] | None:
    best = None
    for threshold in THRESHOLD_CANDIDATES:
        if not _clears_acceptance_margins(threshold, procedural_score, rationale_score):
            continue
        precision, recall = precision_recall(val_probabilities, val_labels, threshold)
        if precision < MIN_PRECISION:
            continue
        candidate = (recall, precision, threshold)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    return best


def _clears_acceptance_margins(threshold: float, procedural_score: float, rationale_score: float) -> bool:
    return (
        threshold - rationale_score >= MIN_ACCEPTANCE_MARGIN
        and procedural_score - threshold >= MIN_ACCEPTANCE_MARGIN
    )


def main() -> None:
    features, labels = load_dataset()
    (train_features, train_labels), (val_features, val_labels), (test_features, test_labels) = split_dataset(
        features, labels
    )
    table = load_table()
    procedural_embedding = table.embed(ACCEPTANCE_PROCEDURAL_EXAMPLE)
    rationale_embedding = table.embed(ACCEPTANCE_RATIONALE_EXAMPLE)

    original = (training_module.LEARNING_RATE, training_module.RIDGE_PENALTY, training_module.ITERATIONS)
    try:
        winner = hyperband(train_features, train_labels, val_features, val_labels)

        # Refit the winner at the full resource budget — this becomes the baked ITERATIONS.
        training_module.LEARNING_RATE = winner.learning_rate
        training_module.RIDGE_PENALTY = winner.ridge_penalty
        training_module.ITERATIONS = MAX_ITERATIONS
        weights, bias = fit_logistic_regression(train_features, train_labels)

        procedural_score = scores_for(weights, bias, procedural_embedding[None, :])[0]
        rationale_score = scores_for(weights, bias, rationale_embedding[None, :])[0]
        val_probabilities = scores_for(weights, bias, val_features)
        best = _select_threshold(val_probabilities, val_labels, procedural_score, rationale_score)
    finally:
        training_module.LEARNING_RATE, training_module.RIDGE_PENALTY, training_module.ITERATIONS = original

    if best is None:
        raise SystemExit("no threshold met both the precision floor and the acceptance margins")

    val_recall, val_precision, threshold = best
    test_precision, test_recall = precision_recall(scores_for(weights, bias, test_features), test_labels, threshold)
    train_precision, train_recall = precision_recall(
        scores_for(weights, bias, train_features), train_labels, threshold
    )

    print(f"hyperband winner: learning_rate={winner.learning_rate:.4g}, ridge_penalty={winner.ridge_penalty:.4g}")
    print(f"selected: iterations={MAX_ITERATIONS}, threshold={threshold}")
    print(
        f"acceptance scores: procedural={procedural_score:.3f} (>= threshold), "
        f"rationale={rationale_score:.3f} (< threshold)"
    )
    print(f"{'split':<6} {'precision':>9} {'recall':>7}")
    print(f"{'train':<6} {train_precision:>9.3f} {train_recall:>7.3f}")
    print(f"{'val':<6} {val_precision:>9.3f} {val_recall:>7.3f}")
    print(f"{'test':<6} {test_precision:>9.3f} {test_recall:>7.3f}")


if __name__ == "__main__":
    main()
