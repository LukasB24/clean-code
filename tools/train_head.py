"""Train the what/why classifier head and write ``src/cleancode/semantics/head.json``.

Embeds every labeled clause of ``tools/data/what_why.jsonl`` through the
vendored backbone table (the exact code path the linter uses at runtime, so
training and inference can never diverge), splits it 80/10/10 with
``cleancode.semantics.training.split_dataset``, and fits the logistic head on
the train split only with ``fit_logistic_regression`` — full-batch gradient
descent from a zero start, so the output is reproducible without a seed. The
held-out val/test splits are never seen during fitting, so their accuracy is
a real generalization estimate rather than the training-set accuracy the
corpus's small size would otherwise make easy to overstate. Needs only numpy:

    PYTHONPATH=src python tools/train_head.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cleancode.semantics.backbone import load_table  # noqa: E402
from cleancode.semantics.training import accuracy, fit_logistic_regression, split_dataset  # noqa: E402

DATASET = Path(__file__).parent / "data" / "what_why.jsonl"
OUTPUT = Path(__file__).parent.parent / "src" / "cleancode" / "semantics" / "head.json"


def load_dataset() -> tuple[np.ndarray, np.ndarray, int]:
    """(features, labels, skipped) for every embeddable clause of the corpus."""
    table = load_table()
    features: list[np.ndarray] = []
    labels: list[int] = []
    skipped = 0
    for line in DATASET.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        embedding = table.embed(record["text"])
        if embedding is None:
            skipped += 1
            continue
        features.append(embedding)
        labels.append(1 if record["label"] == "what" else 0)
    return np.array(features), np.array(labels), skipped


def main() -> None:
    features, labels, skipped = load_dataset()
    print(f"{len(labels)} clauses ({int(labels.sum())} what / {len(labels) - int(labels.sum())} why)"
          f", {skipped} skipped as unembeddable")

    (train_features, train_labels), (val_features, val_labels), (test_features, test_labels) = split_dataset(
        features, labels
    )
    print(f"split: {len(train_labels)} train / {len(val_labels)} val / {len(test_labels)} test")

    weights, bias = fit_logistic_regression(train_features, train_labels)

    accuracies = {
        "train": round(accuracy(weights, bias, (train_features, train_labels)), 4),
        "val": round(accuracy(weights, bias, (val_features, val_labels)), 4),
        "test": round(accuracy(weights, bias, (test_features, test_labels)), 4),
    }
    head = {
        "version": 1,
        "dim": len(weights),
        "weights": [round(float(weight), 8) for weight in weights],
        "bias": round(float(bias), 8),
        "training": {
            "samples": {"train": len(train_labels), "val": len(val_labels), "test": len(test_labels)},
            "accuracy": accuracies,
        },
    }
    OUTPUT.write_text(json.dumps(head) + "\n", encoding="utf-8")
    print(
        f"accuracy: train {accuracies['train']:.3f}, val {accuracies['val']:.3f}, "
        f"test {accuracies['test']:.3f}; wrote {OUTPUT}"
    )


if __name__ == "__main__":
    main()
