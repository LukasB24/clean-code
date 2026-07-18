"""Logistic classifier head over the frozen backbone: P(clause is procedural).

The head (``head.json``) is trained offline by ``tools/train_head.py`` on the
labeled clause corpus in ``tools/data/what_why.jsonl`` and checked in, so
runtime scoring is a single dot product over a clause's backbone embedding —
deterministic and dependency-free beyond numpy.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from importlib import resources

import numpy as np

from cleancode.semantics.backbone import WordTable, load_table


class WhatWhyClassifier:
    """Scores a clause's probability of being a purely procedural description."""

    def __init__(self, table: WordTable, weights: np.ndarray, bias: float) -> None:
        self._table = table
        self._weights = weights
        self._bias = bias

    def score(self, clause: str) -> float | None:
        """P(procedural) in [0, 1], or ``None`` when the clause has no known words."""
        embedding = self._table.embed(clause)
        if embedding is None:
            return None
        logit = float(self._weights @ embedding) + self._bias
        return 1.0 / (1.0 + math.exp(-logit))


@lru_cache(maxsize=1)
def load_classifier() -> WhatWhyClassifier:
    head = json.loads(resources.files("cleancode.semantics").joinpath("head.json").read_text())
    weights = np.asarray(head["weights"], dtype=np.float32)
    return WhatWhyClassifier(load_table(), weights, float(head["bias"]))
