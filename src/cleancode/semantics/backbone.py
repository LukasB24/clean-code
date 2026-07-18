"""Frozen pretrained word-embedding backbone, loaded from the vendored table.

``embeddings.npz`` holds an int8-quantized, PCA-reduced word table distilled
from WordLlama ``l2_supercat_256`` by ``tools/distill_backbone.py``. A clause
is embedded by looking up its words (falling back to heuristic stems, so
"iterates" finds "iterate"), dequantizing, mean-pooling, and L2-normalizing.
"""

from __future__ import annotations

import io
import re
from functools import lru_cache
from importlib import resources

import numpy as np

from cleancode.rules.base import stem_candidates

_WORD = re.compile(r"[a-z]{2,}")


class WordTable:
    """Word -> pretrained vector lookup with mean-pooled clause embedding."""

    def __init__(self, vocab: np.ndarray, vectors: np.ndarray, scales: np.ndarray) -> None:
        self._index: dict[str, int] = {word: row for row, word in enumerate(vocab.tolist())}
        self._vectors = vectors
        self._scales = scales

    @property
    def dim(self) -> int:
        return self._vectors.shape[1]

    def _row_of(self, word: str) -> int | None:
        row = self._index.get(word)
        if row is not None:
            return row
        # Sorted so the fallback is deterministic: a frozenset's iteration
        # order depends on the process's string-hash seed.
        for candidate in sorted(stem_candidates(word)):
            row = self._index.get(candidate)
            if row is not None:
                return row
        return None

    def embed(self, text: str) -> np.ndarray | None:
        """L2-normalized mean of the known word vectors of ``text``, or ``None``.

        ``None`` (rather than a zero vector) when no word of the clause is in
        the table — the caller must treat such a clause as unjudgeable, not
        as semantically empty.
        """
        rows = [row for word in _WORD.findall(text.lower()) if (row := self._row_of(word)) is not None]
        if not rows:
            return None
        vectors = self._vectors[rows].astype(np.float32) * self._scales[rows, None]
        pooled = vectors.mean(axis=0)
        norm = float(np.linalg.norm(pooled))
        if norm == 0.0:
            return None
        return pooled / norm


@lru_cache(maxsize=1)
def load_table() -> WordTable:
    payload = resources.files("cleancode.semantics").joinpath("embeddings.npz").read_bytes()
    with np.load(io.BytesIO(payload)) as archive:
        return WordTable(archive["vocab"], archive["vectors"], archive["scales"])
