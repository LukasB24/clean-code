# Semantic "what vs. why" detection for docstrings and comments (issue #28)

Issue [#28](https://github.com/LukasB24/clean-code/issues/28) asks the linter
to catch LLM-generated docstrings/comments that merely *paraphrase* what the
code does (synonyms, reworded operations) — cases the lexical-overlap rules
(CM301, CM302, CM304) structurally cannot see — while never flagging comments
that carry genuine rationale. Constraints: no heavy ML frameworks at runtime,
sub-millisecond per comment, deterministic and testable, layered on top of
the existing deterministic rules.

This document describes the design as implemented on this branch: a
**pretrained lightweight backbone with a trained classifier head**, plus the
deterministic guards that keep its false-positive rate near zero.

## Architecture

Two tiers. Tier 1 is unchanged: the deterministic AST/lexical rules run
first, and anything they flag never reaches tier 2 (no double reports).
Tier 2 is the new rule **CM307 `docstring-semantic-restatement`**
(`rules/docstrings.py`), backed by `src/cleancode/semantics/`:

- **Backbone (frozen, pretrained):** WordLlama `l2_supercat_256` static token
  embeddings, distilled at build time by `tools/distill_backbone.py` into a
  vendored word table (`semantics/embeddings.npz`, ~9.4k words × 128 dims,
  PCA-reduced and int8-quantized, 1.2 MB). Clause embedding = word lookup
  (with heuristic-stem fallback, so "iterates" finds "iterate") → dequantize
  → mean-pool → L2-normalize (`semantics/backbone.py`). The distillation
  runs fully offline from files bundled in the `wordllama` PyPI wheel;
  `wordllama` is a tools-only dependency, never installed at runtime.
- **Head:** a logistic layer over the 128-dim clause embedding
  (`semantics/classifier.py`), trained by `tools/train_head.py` on the
  labeled clause corpus `tools/data/what_why.jsonl` (~450 clauses) and
  checked in as `semantics/head.json`. Training (`semantics/training.py`)
  is full-batch gradient descent from a zero start with fixed
  hyperparameters — reproducible without a seed, no sklearn/torch anywhere,
  and locked by a test that retrains and compares against the checked-in
  weights.
- **Clause splitting** (`semantics/clauses.py`): sentences, cut again where
  a rationale connective ("because ...", "so ...", "to maximize ...")
  starts, with inline code spans stripped first. A text is flagged only when
  **every** clause reads as procedural narration — one rationale clause
  clears it, which is exactly the composite-comment acceptance criterion.
- **Narration-shape guard** (`semantics/clauses.py`): mean-pooled embeddings
  are blind to word order, so a deterministic check keeps noun-led value
  contracts ("Groups of functions whose bodies collide") away from the
  classifier; only verb-led clauses ("Groups the records by key") are ever
  scored.

### Scope and gating of CM307

- Undecorated function docstrings of at most `max_lines` (default 3) lines —
  a class docstring states responsibility and a decorated function's
  docstring is framework-facing help text (click, `@property`, fixtures).
- Standalone comment *blocks*: consecutive same-column `#` lines are judged
  as the one paragraph a reader sees, so a wrapped rationale is never
  split into misleading fragments.
- Skipped entirely: anything CM301/CM302 at default thresholds already
  catch, TODO/directive comments, texts carrying a why-signal word
  (because, workaround, ...), and texts below `min_words` content words.
- Options: `threshold` (default 0.75), `min_words` (3), `max_lines` (3);
  severity and enablement work like every other rule.

## Acceptance criteria → verification

| Criterion | How it is met |
| --- | --- |
| Flags procedural paraphrases | `"""Adds two numbers and returns the sum."""` over `return a + b` is flagged (held out of the training corpus; asserted in `tests/test_what_why.py` and the `llm_style_paraphrase.py` dirty fixture) |
| Passes composite what+why comments | "…using block-striping to maximize L1 cache hits" passes via clause splitting + the all-clauses rule (same test file; `semantic_docstrings.py` clean fixture) |
| No environment bloat | Runtime deps are exactly `click` + `numpy`; a test asserts no `torch`/`sklearn` module is ever imported and pins the dependency list |
| Performance budget | Scoring is a dict lookup + one 128-dim dot product; a test asserts the mean is far below 1 ms per clause |
| Maintainability | Isolated `semantics/` package, versioned checked-in assets, reproducible training locked by test, registered as an ordinary rule with the standard config/docs/example machinery |

The false-positive bar is enforced by the repo's own dogfood test: the
analyzer, including CM307, passes over its entire own source.

## Retraining / rebuilding

```
pip install numpy wordllama          # tools-only environment
python tools/distill_backbone.py     # rebuild semantics/embeddings.npz
PYTHONPATH=src python tools/train_head.py   # rebuild semantics/head.json
```

Edit `tools/data/what_why.jsonl` to teach the classifier new patterns; the
reproducibility test fails if `head.json` drifts from the corpus.
