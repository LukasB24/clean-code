# Plan: Semantic "what vs. why" detection for docstrings and comments (issue #28)

Issue [#28](https://github.com/LukasB24/clean-code/issues/28) asks the linter to
catch LLM-generated docstrings/comments that merely *paraphrase* what the code
does (synonyms, reworded operations) — cases the current lexical-overlap rules
(CM301, CM302, CM304) structurally cannot see — while never flagging comments
that carry genuine rationale. Constraints: no heavy ML frameworks at runtime,
sub-millisecond per comment, deterministic and testable, layered on top of the
existing deterministic rules.

## Approach in one paragraph

Keep the existing deterministic rules as the fast first tier, unchanged. Add a
second tier: a tiny **linear text classifier implemented in pure Python** that
scores each *clause* of a docstring/comment as "what" (procedural description)
or "why" (rationale). The model's weights are trained offline by a dev-only
script (also pure Python — the dataset is small enough that hand-rolled
logistic regression suffices, so neither `torch` nor `scikit-learn` appears
anywhere, not even as a dev dependency) and checked into the repo as a
versioned JSON data file. Runtime inference is a bag-of-features dot product
plus a threshold: deterministic, dependency-free, and on the order of
microseconds per comment — comfortably inside the sub-millisecond budget. A
docstring is only flagged when **every** clause scores "what"; a single
rationale clause exempts the whole comment, which is exactly the composite-
comment acceptance criterion.

## Architecture

### New package: `src/cleancode/semantics/`

| File | Contents |
| --- | --- |
| `features.py` | Clause splitting + feature extraction (pure functions, no I/O) |
| `classifier.py` | `WhatWhyClassifier`: loads packaged weights, `score(clause) -> float`, `is_procedural(clause) -> bool` |
| `model.json` | Versioned weights + feature vocabulary, shipped inside the wheel, loaded via `importlib.resources` |

Shared text helpers move up rather than get duplicated: the heuristic stemmer
(`_stem_candidates` / `_stemmed`) and the operator-synonym idea currently
private to `rules/comments.py` are promoted into `semantics/features.py` (or
`rules/base.py`), and `rules/comments.py` imports them from there.

### Feature set (hand-engineered, small, auditable)

All features are computed from the clause text plus the AST facts of the code
the docstring documents — no external lookups:

1. **Procedural-verb lexicon hits** — an expanded, curated synonym lexicon of
   operation verbs ("adds", "concatenates", "iterates", "retrieves",
   "computes", …), generalizing today's `FRAMING_VERBS`. Matched through the
   stemmer so inflections don't need entries.
2. **Code-anchored synonym overlap** — reuse the `_OPERATOR_SYNONYMS` trick at
   function granularity: derive facts from the documented function's AST
   (contains a loop, arithmetic, `return`, calls to `sum`/`sorted`/`open`/…)
   and count clause words that are natural-language synonyms of those facts.
   This is what catches "Adds two numbers and returns the sum." over
   `return a + b` even with zero identifier overlap.
3. **Rationale markers** — an expanded `_WHY_SIGNALS` lexicon: causal
   connectives (because, so that, in order to), constraint/intent vocabulary
   (avoid, ensure, guarantee, invariant, thread-safe, cache, performance,
   precision, backwards-compatible, spec, RFC, …), units and domain numerals.
4. **Novel-vocabulary ratio** — fraction of clause content words that appear
   neither in the signature/body words (already computed by CM301's
   `_body_source_words`) nor in any synonym lexicon. High novelty is evidence
   of external context, i.e. "why".
5. **Structural cues** — clause length, presence of numerals/units, whether
   the clause is introduced by a purpose connective ("to maximize …").

### Classifier

Plain logistic regression: `sigmoid(w · x + b)` over the ~few-dozen features
above. Weights live in `model.json` with a schema version. Inference is a
handful of dict lookups and one dot product — deterministic float math, no
randomness, no allocation-heavy work. A conservative decision threshold
(configurable) biases toward false negatives: for a linter, silently missing a
noisy docstring is far cheaper than flagging a good one.

### Clause-level compositionality

`features.py` splits text into clauses on sentence boundaries and purpose
connectives (`.`, `;`, "to", "so that", "because", "in order to"). The rule
flags only when **all** clauses classify as procedural. So:

- `"""Adds two numbers and returns the sum."""` → one clause, procedural → **flag**
- `"""Computes matrix multiplication using block-striping to maximize L1 cache
  hits."""` → the "to maximize L1 cache hits" clause carries rationale markers
  and novel vocabulary → **pass**

### New rule: CM307 `docstring-semantic-restatement`

Lives beside CM301 in `rules/docstrings.py` (registered in
`rules/__init__.py`; CM307 is the next free ID). Behavior:

- **Tier gating**: only examines docstrings/comments that Tier 1 did *not*
  already flag — deterministic checks stay the first line of defense, and no
  docstring is ever double-reported. Exempt prefixes (TODO, directives) and
  `_WHY_SIGNALS` short-circuits carry over from CM302.
- **Scope**: function/class docstrings first; also non-exempt standalone
  comments of ≥ `min_words` words, judged against their annotated code's AST
  facts (the same `_annotated_code` resolution CM302 uses).
- **Options**: `{"threshold": <probability>, "min_words": 3}`; default
  severity `WARNING` with a deliberately conservative threshold. Fully
  disableable per the existing config machinery.
- **Guidance string** for `guide.py`, mirroring CM301's tone: document why,
  edge cases, units, invariants — never a synonym-paraphrase of the body.

## Offline training (dev-only, zero new dependencies)

- `tools/data/what_why.jsonl` — a curated labeled dataset of clauses:
  procedural paraphrases harvested from the existing dirty fixtures and real
  LLM output, rationale clauses from the clean fixtures and real codebases.
  A few hundred examples is plenty for a linear model with engineered features.
- `tools/train_what_why.py` — pure-Python logistic regression via batch
  gradient descent, fixed seed and fixed iteration count → **bit-for-bit
  reproducible weights**. Regenerates `semantics/model.json`. Not shipped in
  the wheel; `pyproject.toml` runtime dependencies stay exactly `click>=8.1`.

Because both training and inference are dependency-free, the "no environment
bloat" acceptance criterion is satisfied trivially: `pip show torch
scikit-learn` finds nothing because they are never installed at any stage.

## Testing

1. **Golden classifier tests** (`tests/test_semantics.py`): exact expected
   feature vectors and scores for a table of clauses — deterministic outputs,
   including both acceptance-criteria examples from the issue.
2. **Rule tests**: CM307 fires on synonym-paraphrase docstrings that CM301
   passes; stays silent on composite what+why docstrings, on rationale-only
   docstrings, and on anything CM301 already flagged (no double report).
3. **Fixtures**: new `tests/fixtures/dirty/llm_style_paraphrase.py` (flagged)
   and a clean counterpart with composite rationale docstrings (not flagged),
   wired into `test_fixtures.py`.
4. **Performance guard**: run the classifier over ~1,000 representative
   clauses and assert mean time per clause is far below 1 ms (generous bound
   to avoid CI flakiness; expected actual cost is single-digit microseconds).
5. **Dependency guard**: a test that imports `cleancode`, runs an analysis,
   and asserts no module named `torch`/`sklearn`/`numpy` is in `sys.modules`,
   plus an assertion that `pyproject.toml` runtime deps are unchanged.
6. **Model reproducibility**: a test that retrains on the checked-in dataset
   and asserts the weights match `model.json`, so the data file can never
   silently drift from its source.

## Documentation

- `docs/RULES.md`: CM307 entry with examples and options.
- `CHANGELOG.md`: feature entry.
- Brief note in `semantics/__init__.py` docstring describing the two-tier
  design and how to retrain.

## Acceptance criteria mapping

| Criterion | How the plan satisfies it |
| --- | --- |
| Accurate identification of procedural docstrings | Code-anchored synonym features catch paraphrases with zero identifier overlap (`"""Adds two numbers and returns the sum."""` over `return a + b`) |
| Composite context awareness | Clause splitting + all-clauses-must-be-procedural flagging; one rationale clause exempts the comment |
| No environment bloat | Pure-Python inference *and* training; runtime deps remain `click` only; dependency-guard test enforces it |
| Maintainability | Isolated `semantics/` package with pure functions, versioned checked-in weights, golden deterministic tests, reproducible training script; integrates as an ordinary registered rule |

## Implementation order

1. Promote shared stemmer/synonym helpers; build `semantics/features.py` with clause splitting + feature extraction (tests alongside).
2. Build `semantics/classifier.py` with a hand-initialized weight file to get the pipeline running end-to-end.
3. Curate `what_why.jsonl`, write `tools/train_what_why.py`, regenerate `model.json`, lock with the reproducibility test.
4. Add rule CM307, register it, wire tier gating against CM301/CM302 results.
5. Fixtures, performance guard, dependency guard.
6. Docs + changelog; tune threshold on the fixture corpus until false positives on clean fixtures are zero.

## Risks and mitigations

- **False positives ruin linter UX** → conservative threshold, all-clauses
  rule, `WHY_SIGNALS` short-circuit before scoring, severity configurable,
  rule disableable. Tune against the clean fixtures with a zero-FP bar.
- **English-only lexicons** → same limitation the existing rules already
  accept; documented in the rule description.
- **Model drift / opaque data file** → weights are reproducible from a
  checked-in script + dataset with a locking test; features are named and
  auditable rather than learned embeddings.
