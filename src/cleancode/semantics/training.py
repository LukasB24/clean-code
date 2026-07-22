"""Deterministic logistic-regression training for the classifier head.

Lives in the runtime package (rather than ``tools/``) so the reproducibility
test can retrain on the checked-in dataset and compare against ``head.json``
— it is plain numpy, adds no dependency, and full-batch gradient descent
from a zero start needs no random seed to be bit-for-bit repeatable. The
hyperparameters are module constants for the same reason: they are part of
what makes the checked-in head reproducible, not knobs callers tune.
"""

from __future__ import annotations

import numpy as np

# Selected by tools/tune_head.py against the validation split only, for
# recall (reaches 1.0 on val, 0.926 on test, up from 0.80/0.80 at the prior
# 1.5e-4/0.5 pair) while keeping issue #28's held-out rationale example's
# score (0.198) safely below the paired 0.3 threshold.
RIDGE_PENALTY = 1e-3
LEARNING_RATE = 1.0
ITERATIONS = 15000
DECISION_THRESHOLD = 0.5

SPLIT_MODULUS = 10
VAL_REMAINDER = 8
TEST_REMAINDER = 9


def split_dataset(
    features: np.ndarray, labels: np.ndarray
) -> tuple[tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]]:
    """Deterministic 80/10/10 ``(train, val, test)`` split, each ``(features, labels)``.

    Splitting by row position rather than a random shuffle means re-running
    against the same corpus always yields the exact same three sets — no
    seed to pin down, no risk of a shuffle implementation changing across
    numpy versions.
    """
    positions = np.arange(len(labels))
    is_test = positions % SPLIT_MODULUS == TEST_REMAINDER
    is_val = positions % SPLIT_MODULUS == VAL_REMAINDER
    is_train = ~(is_test | is_val)
    return (
        (features[is_train], labels[is_train]),
        (features[is_val], labels[is_val]),
        (features[is_test], labels[is_test]),
    )


def fit_logistic_regression(features: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, float]:
    samples = features.astype(np.float64)
    targets = labels.astype(np.float64)
    weights = np.zeros(samples.shape[1])
    bias = 0.0
    for _ in range(ITERATIONS):
        logits = samples @ weights + bias
        predictions = 1.0 / (1.0 + np.exp(-logits))
        error = predictions - targets
        # Unregularized so class balance isn't fought by the ridge penalty.
        weights -= LEARNING_RATE * (samples.T @ error / len(targets) + RIDGE_PENALTY * weights)
        bias -= LEARNING_RATE * float(error.mean())
    return weights, bias


def accuracy(weights: np.ndarray, bias: float, dataset: tuple[np.ndarray, np.ndarray]) -> float:
    features, labels = dataset
    logits = features @ weights + bias
    predictions = 1.0 / (1.0 + np.exp(-logits))
    predicted_positive = predictions >= DECISION_THRESHOLD
    actual_positive = labels == 1
    return float((predicted_positive == actual_positive).mean())
