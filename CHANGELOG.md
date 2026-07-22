# Changelog

All notable changes to clean-code are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/). The project
follows [Semantic Versioning](https://semver.org/); while pre-1.0 (`0.x`),
a minor version bump may still change a rule's default severity or default
options, not just add new ones — check the entry below before upgrading.
`1.0.0` will mark the point where that stops.

Rule IDs are stable once shipped (a rule keeps its ID across releases,
whether pre- or post-1.0).

## [Unreleased]

### Added

- Docstring paraphrase detection for issue #28, in two tiers:
  - `CM301` (`docstring-restates-name`) now also catches a docstring that
    paraphrases the function body in synonyms rather than restating it
    verbatim (`"""Adds two numbers and returns the sum."""` over `return a +
    b`), reusing CM302's operator/keyword-synonym table against the whole
    body instead of one annotated line. New `body_overlap` option (default
    `0.6`); why-signal docstrings are exempt, same as CM302.
  - `CM307` `docstring-semantic-restatement` — a second, semantic tier for
    the more diffuse paraphrases CM301's operator-anchored check can't reach
    (loose verb-synonym narration with no strong operator/keyword anchor),
    bringing the total to 52. A vendored pretrained-embedding backbone
    (distilled from WordLlama `l2_supercat_256` into a 1.2 MB int8 word
    table by `tools/distill_backbone.py`) with a logistic classifier head
    (trained reproducibly by `tools/train_head.py` on the labeled clause
    corpus in `tools/data/what_why.jsonl`) scores each clause of a
    docstring/comment as procedural narration vs. rationale, passing
    composite comments that also carry rationale ("... to maximize L1 cache
    hits"). Inference is pure numpy — no ML framework anywhere,
    deterministic outputs, microseconds per comment. Anything CM301/CM302
    already flag (including CM301's new body-overlap check) is skipped, so
    the two tiers never double-report the same paraphrase.
- `numpy>=1.26` as a runtime dependency (for CM307's embedding lookups); the
  runtime environment remains free of `torch`/`scikit-learn`/any ML
  framework, now enforced by a test.
- `NOTICE` and `src/cleancode/semantics/THIRD_PARTY_NOTICES/`: CM307's
  vendored `embeddings.npz` is a derivative of Llama-2-derived token
  embeddings (via WordLlama's `l2_supercat_256`), so it ships with the
  attribution notice, a full copy of the LLAMA 2 Community License
  Agreement, and the Acceptable Use Policy it incorporates by reference —
  required by that license, and separate from clean-code's own Apache-2.0
  license.
- `tools/train_head.py` now fits the classifier head on an 80/10/10
  train/val/test split (`cleancode.semantics.training.split_dataset`,
  deterministic by row position, no seed needed) instead of the full
  corpus, and `head.json`'s `training` block reports all three accuracies.
  The previous single `accuracy` figure was training accuracy only —
  measured on the same 449 examples the head was fit on — which
  overstated how well the classifier generalizes.
- `RIDGE_PENALTY` raised from `1e-4` to `1.5e-4` (chosen against the
  validation split, never test) to close some of that train/test gap: with
  `1e-4`, train accuracy reached 0.9194 while test sat at 0.7500; at
  `1.5e-4`, val accuracy is unchanged (0.8444) and test rises to 0.7727,
  the largest penalty short of pushing issue #28's own held-out acceptance
  example below CM307's default threshold.
- `CM307`'s default `threshold` lowered from `0.75` to `0.5`: measured on
  the labeled corpus's held-out val/test splits, `0.75` missed 40-45% of
  genuinely procedural clauses (recall 0.60 val / 0.55 test); `0.5` raises
  recall to 0.80 on both, for a precision cost only on test (0.786 →
  0.727 — val precision actually improves slightly, 0.800 → 0.842).
  Deliberate: for a linter meant to flag comments an LLM should rework, a
  false positive costs a wasted re-check, while a false negative is a
  paraphrase nobody looks at again.
- `tools/data/what_why.jsonl` grown from 449 to 556 hand-curated clauses
  (270 what / 286 why), adding coverage the original corpus was thin on:
  synonym-heavy narration, noun-led restatements, and domain vocabulary
  (networking, databases, concurrency, security, serialization) the
  classifier hadn't seen. New `tools/tune_head.py` grid-searches
  `RIDGE_PENALTY` and `CM307`'s `threshold` against the validation split
  only (never test), maximizing recall (ties broken by precision, then a
  floor rejects any pair leaving too little margin over issue #28's
  held-out rationale acceptance example's score) — the same recall-first
  tradeoff the repo owner chose for the `0.5` threshold above.
  `RIDGE_PENALTY` raised `1.5e-4` → `1e-3` and `CM307`'s default `threshold`
  lowered `0.5` → `0.3`: val recall reaches `1.0` (from `0.80`) and test
  recall `0.926` (from `0.80`), while the acceptance example's score (0.198)
  still clears the new threshold by a safe margin.
- Seven new rules targeting patterns common in freshly-generated Python,
  bringing the total to 51:
  - `ST109` `redundant-else` — a plain two-way `if`/`else` whose `if` branch
    always exits (return/raise/break/continue). Any `if` that's itself part
    of an `elif` chain is exempt entirely, so a multi-way dispatch ladder
    ending in `else` is never flagged, even when every branch returns.
  - `CM306` `banner-comment` — a decoration-only (`# ----------`) or
    decoration-framed (`# ---- Step 1 ----`) comment; reuses CM303/CM305's
    directive-comment exemptions.
  - `PY903` `oversized-try` — a `try` spanning more than `max_statements`
    (default 3) top-level statements feeding a bare or broad
    `except Exception`/`BaseException` handler, which can't tell which step
    actually failed. A narrowly-typed `except`, or a short `try` wrapping a
    broad handler, is not flagged.
  - `SM620` `returned-temp` — `name = expr` immediately followed by
    `return name` with no other use of `name`. An annotated assignment
    (`name: T = expr`) is exempt.
  - `SM621` `compatibility-alias` — a module-level `alias = original`
    pointing at a function/class defined in the same file. ALL_CAPS
    targets, `_`-prefixed targets, and annotated assignments are exempt.
  - `SM622` `trivial-property-pair` — a `@property`/`@x.setter` pair that
    only mirrors `self._x` with no logic in either accessor. A getter-only
    read-only property is a legitimate idiom and is exempt.
  - `SD803` `class-as-namespace` — a class with no bases, decorators, or
    class-level state whose entire body is `min_methods`-or-more (default
    2) `@staticmethod`s; the module is already the namespace it's imitating.
  - `SM620`/`SM621`/`SM622` live in a new `src/cleancode/rules/noise.py`
    module (naming/indirection ceremony, distinct from the AST-shape
    smells in `semantic.py`/`clarity.py`).
- `clean-code guide [PATH]` — a generation-time briefing for an LLM, one
  imperative bullet per *enabled* rule ("Nest at most 2 levels...", "Never
  write a bare `except:`..."), rendered with the project's own configured
  option values so a loosened `max_depth` or a disabled rule shows up
  correctly. `--agents-md` wraps the same brief with standing instructions
  for pasting into a project's `CLAUDE.md`/`AGENTS.md`
  (`clean-code guide --agents-md >> CLAUDE.md`). Every rule carries a new
  `guidance` string (or is explicitly folded into a sibling's — see
  `guide.COVERED_BY_SIBLING`), enforced by `tests/test_guide.py`.
- `clean-code explain <RULE_ID> [<RULE_ID> ...]` — prints a rule's full
  description, its `guide` sentence, its configured-vs-default options, and
  a minimal BAD/GOOD before/after example an LLM can pattern-match against.
  Every rule has an `Example` in the new `src/cleancode/examples/` package;
  `tests/test_examples.py` runs every `bad` and `good` snippet through the
  engine and requires the rule to fire on one and not the other, doubling
  as a permanent regression net.
- Context-aware suggestions for three high-value rules, falling back to the
  previous generic text when no hint is available: `NM202`/`NM201` derive a
  rename candidate from the flagged binding's own annotation (`bounds: list[Trade]`
  → `trades`) or the call it's assigned from (`data = load_users(path)` →
  `users`, from `load_users`); `SM607` derives a `MAX_`/`MIN_`-prefixed
  constant name from the idiomatic `name <op> literal` comparison shape
  (`if retries > 5` → `MAX_RETRIES = 5`). `Binding` now carries the AST node
  it was bound at.
- `SM618` `thin-delegation-wrapper` — flags a private function whose whole
  body is `return <one call to another function>`, a hop that only renames
  work. Public functions, decorated functions, dunders, builtin callees, and
  calls on the function's own parameters are exempt.
- `SM619` `buried-value-fallback` — flags an `or`/`and` value fallback used
  as an arithmetic operand or subscript index (`(node.end_lineno or
  node.lineno) + 1`), where the boolean operator is easy to misread. A bare
  `x = a or b` and ordinary boolean conditions are exempt.
- `CM301` now also checks class docstrings (reference words: class name +
  its directly-defined method names), and flags a docstring longer than two
  lines when *every* line stays within the signature/class-name vocabulary
  plus generic filler.
- `CM301`'s short-docstring check now also judges a function's docstring
  against its own source text (identifier- and keyword-shaped words, the
  same scan `CM302` uses on one code line), not just its name and
  parameters — catching a docstring that paraphrases the return value,
  a local variable, or a branch the code takes instead of the signature.
- `ST108` `max-module-length` — flags a module longer than `max_lines`
  (default 500); a file that keeps absorbing helpers becomes a grab-bag.
- `DP702` `identical-function-implementation` — flags function bodies that
  are exactly identical, identifiers included (default 2+ statements).
  Complements `DP701`; groups long enough for `DP701` are left to it so a
  copy-paste is never reported twice.
- `CM305` `file-comment-density` — flags a file whose overall comment/code
  line ratio exceeds `max_ratio` (default 0.2), catching comment sprawl
  that per-function `CM303` misses. Directive comments and docstrings don't
  count; the suggestion instructs the fixer to analyze every comment in the
  file and keep only those that say something the code cannot.
- `SM614`–`SM617`, the expression clarity family — catches complexity that
  was *compressed* to satisfy the structural limits instead of removed:
  `SM614` `bool-arithmetic` (a comparison added to a counter), `SM615`
  `nested-ternary`, `SM616` `callable-indirection` (returning a `lambda`/
  `functools.partial`/bare function reference instead of doing work), and
  `SM617` `deep-expression` (expressions nested more than `max_depth`
  levels in one statement; flat condition chains and module-level constant
  tables stay exempt).
- Suppression directives now also work from the line above: a standalone
  `# cleancode: disable[=IDS]` comment suppresses the next code line below
  it (inline directives stay same-line-only).

### Changed

- `CM301` tightened further: default `overlap` lowered from 0.7 to 0.6, and
  a new `private_overlap` (default 0.35) judges any `_`-prefixed function or
  class at a much stricter bar — a private name has no external reader to
  write prose for, only its own (usually short) body. Motivated by a real
  review finding: a private helper's docstring that paraphrased its own
  body in different words, with no literal signature-word reuse, scored
  0.625 against the old single 0.7 threshold and slipped through entirely.
  `CM302`'s default `overlap` also lowered, 0.7 to 0.5, for the same reason
  applied to inline/standalone comments. Both are pre-1.0 behavior changes;
  re-run `clean-code check` after upgrading — code that passed before may
  not now.
- `CM301`'s default `overlap` lowered from 0.8 to 0.7 — pre-1.0, so this is
  a behavior change, not just a new rule; it now also scores the whole text
  of a two-line docstring instead of only its first line.
- `DP701`/`DP702`'s two dump functions merged into one (`SM618` motivated
  this: two near-duplicate one-liners were themselves the smell), threading
  an `exact` flag instead of passing a callable through the fingerprinting
  pipeline.
- The new clarity rules forced their own cleanup of this codebase (the
  dogfood gate at work): `DP701`/`DP702`'s fingerprint-factory layer is
  replaced by two dump functions with a shared signature passed directly
  (`SM616`), boolean-counting in `CM305` became explicit `if`s (`SM614`),
  and three depth-5 one-liners in `duplication.py`/`structure.py`/
  `template.py` were unpacked into named intermediates (`SM617`).
  Duplicate-detection output is byte-identical before and after.
- `rules/semantic.py` split by concern: `SM609`/`SM610` moved to
  `rules/pytorch.py`, `SM611`–`SM613` to `rules/bindings.py`. Rule ids,
  class names, and behavior are unchanged.
- `DP701` now preserves called function/method names when normalizing
  bodies, so two same-shaped functions invoking different APIs no longer
  fingerprint as duplicates. A call's receiver chain is preserved too when
  it is rooted at an imported name (`json.dumps(...)` vs `yaml.dumps(...)`
  are different APIs), while variable receivers (`fh.write` vs `out.write`)
  still normalize as renames.
- `ST101` violations now attribute their symbol to the innermost
  function/class containing the offending block, instead of always the
  outermost function.
- `SM605`'s suggestion mentions `''.join()` for string concatenation,
  where `sum()` would raise.

### Fixed

- `CM302` no longer double-reports a banner/section-divider comment that
  CM306 already flags — a banner that happens to share vocabulary with a
  nearby line (`# --- sweep overrides ---` above a `sweep_override = ...`
  line) was scoring as a restatement too, so the same comment produced two
  warnings.
- Checking a medium project no longer takes double-digit seconds
  (`clean-code check src` on this repo: 13.5s → 0.9s). `DP701`'s
  fingerprinting deep-copied each statement's AST, and the `parent`
  back-reference every node carries dragged the entire module graph into
  every copy; fingerprints are now rendered from the tree in place, with
  no copy. Per-file rules also share one cached function/binding walk per
  file instead of re-walking the tree per rule.
- `ST105` no longer counts a nested function's branches toward the
  enclosing function's cyclomatic complexity (each function scores its own
  body; lambdas still count toward their enclosing function).
- `ST101` no longer reports the same deep block twice (once for the outer
  function and once for a nested function); nested functions keep
  inheriting the enclosing visual depth.
- `ST101` no longer crashes when the first offender is a `match` case
  (anchored at the case's pattern now).
- A non-UTF-8 or unreadable file no longer aborts the whole run with a
  traceback; it is reported as a per-file error (exit code 2) and the
  remaining files are still checked.
- Relative `exclude` patterns (`migrations/**`, as documented) now work:
  patterns are matched against the path relative to the project root (the
  directory of the `pyproject.toml`/`--config` file) in addition to the
  absolute path.
- `SM612` no longer flags a local variable that is explicitly `del`ed.
- `SM616` no longer misreports guarded dispatch (`if cond: return handler`)
  as "does nothing but hand back" — the bare-forward check now requires the
  `return` to be the function's sole top-level statement.
- `SM616` only calls a call `functools.partial` when it resolves to one
  through the module's imports; an unrelated `something.partial(...)`
  method is no longer flagged.
- `ST101` treats a `ClassDef` as a scope boundary (matching `ST105`), so
  methods of a locally-defined class are measured from their own baseline
  instead of inheriting the enclosing function's depth.
- `example.toml` regenerated — it had drifted and was missing the four
  0.2.0 rules (`SM612`, `SM613`, `PY901`, `PY902`); a new test now pins it
  to the generator's output.
- README banner uses an absolute `raw.githubusercontent.com` URL again so
  it renders on PyPI (the 0.2.1 fix had been lost in a later edit).

## [0.2.1] - 2026-07-15

### Fixed

- README preview image renamed from `assets/banner.svg` to
  `assets/preview.svg` — the old filename matched the ad-network
  pattern in default ad-blocker filter lists, so the image was
  silently blocked for some readers.
- The preview image now uses an absolute `raw.githubusercontent.com`
  URL instead of a relative path, so it renders correctly on the PyPI
  project page as well as on GitHub (PyPI's README renderer doesn't
  resolve relative paths against the repo the way GitHub does).

## [0.2.0] - 2026-07-14

First release published to PyPI. Still pre-1.0: functional and
dogfooded on its own source, but the rule set and defaults may still
shift before the API is called stable.

### Added

- Repository infrastructure for outside contributors: GitHub Actions CI
  (test matrix across Python 3.11–13, `ruff` lint, and a `clean-code`
  self-check job), `CONTRIBUTING.md`, issue templates (bug report, feature
  request, new-rule proposal), a pull request template, and `SECURITY.md`.
- `PY901` `bare-except` — flags a bare `except:` that swallows
  `KeyboardInterrupt`/`SystemExit` along with genuine bugs.
- `PY902` `empty-exception-handler` — flags a handler whose body is entirely
  inert (`pass`, `...`, or a lone string literal) with no log, fallback, or
  re-raise.
- `SM612` `unused-binding` — flags unused imports and unused local
  variables/bindings, with exemptions for `__init__.py` re-exports,
  `__all__`-exported names, `global`/`nonlocal`, forward-reference string
  annotations, and functions that call `locals`/`eval`/`exec`.
- `SM613` `builtin-shadowing` — flags a binding site that shadows a Python
  builtin (`id`, `type`, `list`, ...), verified against the live `builtins`
  module rather than a hardcoded list.
- `DP701` `duplicate-function-body` — a `ProjectRule` that flags copy-pasted
  function bodies (once names are ignored) across every file in one
  `check` run.
- `SD801` `type-switch-violates-ocp` — flags a same-variable
  `isinstance`/`type()` type-switch (an Open/Closed Principle smell);
  exempts dispatch over `ast.*` node types.
- `SD802` `low-cohesion-class` — flags a class whose methods split into 2+
  genuine multi-member clusters sharing no state or calls; exempts
  property getter/setter pairs and classes with a configurable
  `exempt_name_suffixes` (default `Mixin`).

### Fixed

- `SD802` cohesion-clustering logic corrected after initial release.

## [0.1.0] - Baseline

Initial public shape of the tool, combining everything shipped before this
changelog started. Covers:

### Added

- Core analyzer: `analyze_source`/`analyze_path` (single-parse-per-file via
  `ast` + `tokenize`), `[tool.cleancode]` config merging with unknown-key
  rejection, and line-scoped `# cleancode: disable=...` suppressions.
- CLI (`clean-code`): `check` (human + `--json` output, `--select`,
  `--ignore`, `--no-suppress`, `--fail-on`, `--min-severity`), `rules`, and
  `config-template`.
- Structure rules: `ST101` max-nesting-depth, `ST102` max-function-length,
  `ST103` max-class-length, `ST104` max-parameters, `ST105` max-complexity,
  `ST106` do-one-thing, `ST107` too-many-guard-clauses.
- Naming rules: `NM201` short-name, `NM202` meaningless-name, `NM203`
  cryptic-abbreviation — all binding-site-only, with loop/comprehension/
  lambda/`except ... as e`/`TypeVar`/`ALL_CAPS` exemptions.
- Comment rules: `CM301` docstring-restates-name, `CM302`
  comment-restates-code, `CM303` comment-density, `CM304`
  boilerplate-param-docs — deterministic word-overlap scoring, not
  LLM-judged.
- Slicing rules: `SL401` complex-subscript, `SL402` chained-subscript.
- Type-hint rule: `TY501` uninformative-any.
- Semantic-smell rules (`SM6xx`): `SM601` comprehension-density, `SM602`
  anonymous-tuple-indexing, `SM603` magic-string-branching, `SM604`
  redundant-boolean-ternary, `SM605` reduce-instead-of-sum, `SM606`
  repeated-collection-iteration, `SM607` magic-number, `SM608`
  non-idiomatic-emptiness-check, `SM609` eager-dataset-loading, `SM610`
  premature-device-placement, `SM611` redundant-isinstance-check.
- Claude Code skill (`.claude/skills/clean-code`) so `clean-code` can run as
  part of an agent session, generating and validating code in one loop.

### Fixed

- Assorted README accuracy passes to keep the rule table and behavioral
  notes in sync with the implementation.
