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

RIDGE_PENALTY = 1e-4
LEARNING_RATE = 1.0
ITERATIONS = 15000


def fit_logistic_regression(features: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, float]:
    """Full-batch gradient descent on the ridge-regularized logistic loss.

    ``features`` is (n, dim) float, ``labels`` is (n,) with 1 = procedural
    ("what") and 0 = rationale ("why"). Returns ``(weights, bias)``. The bias
    is unregularized so class balance isn't fought by the penalty.
    """
    samples = features.astype(np.float64)
    targets = labels.astype(np.float64)
    weights = np.zeros(samples.shape[1])
    bias = 0.0
    for _ in range(ITERATIONS):
        logits = samples @ weights + bias
        predictions = 1.0 / (1.0 + np.exp(-logits))
        error = predictions - targets
        weights -= LEARNING_RATE * (samples.T @ error / len(targets) + RIDGE_PENALTY * weights)
        bias -= LEARNING_RATE * float(error.mean())
    return weights, bias
