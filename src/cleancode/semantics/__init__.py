"""Semantic what/why scoring for docstrings and comments (second tier of CM307).

The deterministic lexical rules (CM301/CM302/CM304) are the first tier: fast
AST and word-overlap checks that catch comments restating the identifiers
around them. This package is the second tier, for the paraphrases those
checks structurally cannot see ("Adds two numbers and returns the sum." over
``return a + b``): a frozen pretrained embedding backbone (WordLlama
``l2_supercat_256``, distilled by ``tools/distill_backbone.py`` into the
vendored ``embeddings.npz`` word table) with a logistic classifier head on
top (trained by ``tools/train_head.py`` on ``tools/data/what_why.jsonl``,
checked in as ``head.json``).

Inference is a word-table lookup, a mean-pool, and one dot product — pure
numpy, no ML framework, deterministic, and microseconds per clause. To
retrain: edit the dataset and run ``python tools/train_head.py``; to rebuild
the backbone table: ``python tools/distill_backbone.py`` (needs ``wordllama``,
a tools-only dependency).
"""
