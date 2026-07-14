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

Nothing yet.

## [0.2.0] - 2026-07-14

First release published to PyPI. Still pre-1.0: functional and
dogfooded on its own source, but the rule set and defaults may still
shift before the API is called stable.

### Added

- Repository infrastructure for outside contributors: GitHub Actions CI
  (test matrix across Python 3.11–3.13, `ruff` lint, and a `clean-code`
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
