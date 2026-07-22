"""Search RIDGE_PENALTY and the decision threshold for CM307's best recall.

Dev-only tooling (numpy only, never installed at runtime): fits on the train
split for each candidate `RIDGE_PENALTY`, then scores every candidate
threshold against the validation split only, selecting the pair that
maximizes recall (ties broken by precision) — matching the repo owner's
call that a false positive here just costs an LLM a wasted re-check while a
missed paraphrase gets no second look. Two guardrails keep the search from
picking a degenerate "flag everything" point: a `MIN_PRECISION` floor, and
`MIN_ACCEPTANCE_MARGIN`, which rejects any pair that would leave issue #28's
held-out rationale acceptance example ("to maximize L1 cache hits") scoring
too close to the threshold to survive minor numeric drift. Test is scored
last, purely for reporting — it is never used to choose anything, so it
stays a clean generalization estimate.

    PYTHONPATH=src python tools/tune_head.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import cleancode.semantics.training as training_module  # noqa: E402
from cleancode.semantics.backbone import load_table  # noqa: E402
from cleancode.semantics.training import ITERATIONS, LEARNING_RATE, fit_logistic_regression, split_dataset  # noqa: E402

DATASET = Path(__file__).parent / "data" / "what_why.jsonl"
ACCEPTANCE_RATIONALE_EXAMPLE = "to maximize L1 cache hits"

RIDGE_CANDIDATES = [1e-4, 1.5e-4, 3e-4, 5e-4, 1e-3, 2e-3, 3e-3, 5e-3, 1e-2]
THRESHOLD_CANDIDATES = [round(value, 2) for value in np.arange(0.15, 0.71, 0.05)]
MIN_PRECISION = 0.6  # floor below which a recall gain is not worth the false-positive cost
MIN_ACCEPTANCE_MARGIN = 0.05  # threshold must clear the acceptance example's score by at least this much


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
    logits = features @ weights + bias
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


def main() -> None:
    features, labels = load_dataset()
    (train_features, train_labels), (val_features, val_labels), (test_features, test_labels) = split_dataset(
        features, labels
    )
    table = load_table()
    acceptance_embedding = table.embed(ACCEPTANCE_RATIONALE_EXAMPLE)

    best = None
    # fit_logistic_regression reads RIDGE_PENALTY as a module global, so each
    # candidate is applied by patching the module before fitting.
    original_ridge = training_module.RIDGE_PENALTY
    try:
        for ridge in RIDGE_CANDIDATES:
            training_module.RIDGE_PENALTY = ridge
            weights, bias = fit_logistic_regression(train_features, train_labels)
            acceptance_score = scores_for(weights, bias, acceptance_embedding[None, :])[0]
            val_probabilities = scores_for(weights, bias, val_features)
            for threshold in THRESHOLD_CANDIDATES:
                if threshold - acceptance_score < MIN_ACCEPTANCE_MARGIN:
                    continue
                precision, recall = precision_recall(val_probabilities, val_labels, threshold)
                if precision < MIN_PRECISION:
                    continue
                candidate = (recall, precision, ridge, threshold, weights, bias)
                if best is None or candidate[:2] > best[:2]:
                    best = candidate
    finally:
        training_module.RIDGE_PENALTY = original_ridge

    if best is None:
        raise SystemExit("no candidate met both the precision floor and the acceptance margin")

    _, val_precision, ridge, threshold, weights, bias = best
    val_recall = precision_recall(scores_for(weights, bias, val_features), val_labels, threshold)[1]
    test_precision, test_recall = precision_recall(scores_for(weights, bias, test_features), test_labels, threshold)
    train_precision, train_recall = precision_recall(
        scores_for(weights, bias, train_features), train_labels, threshold
    )

    print(f"learning_rate={LEARNING_RATE} iterations={ITERATIONS} (unchanged, already at convergence)")
    print(f"selected: RIDGE_PENALTY={ridge}, threshold={threshold}")
    print(f"{'split':<6} {'precision':>9} {'recall':>7}")
    print(f"{'train':<6} {train_precision:>9.3f} {train_recall:>7.3f}")
    print(f"{'val':<6} {val_precision:>9.3f} {val_recall:>7.3f}")
    print(f"{'test':<6} {test_precision:>9.3f} {test_recall:>7.3f}")


if __name__ == "__main__":
    main()
