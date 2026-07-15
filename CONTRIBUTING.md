# Contributing to clean-code

Thanks for looking at this. clean-code is a small, deliberately dependency-light
project — most contributions fall into one of two buckets: **new rules** and
**bug fixes to existing rules**. This doc covers both, plus the everyday dev
loop.

## Dev setup

```bash
git clone https://github.com/LukasB24/clean-code.git
cd clean-code
pip install -e ".[dev]"
```

That installs the package in editable mode plus `pytest` and `ruff`.

## Everyday commands

```bash
pytest -q                    # run the test suite
ruff check src tests scripts # lint (imports, unused names, obvious mistakes)
clean-code check src         # dogfood: the tool checking its own source
python scripts/benchmark.py  # before/after score over the benchmark fixtures
```

All four run in CI on every PR (`.github/workflows/ci.yml`, matrix over
Python 3.11–3.13). A PR won't merge with any of them red.

## Project layout

```
src/cleancode/
  models.py       # Violation, Severity, FileContext, ParsedFile — the shared data model
  config.py       # pyproject.toml [tool.cleancode] parsing, per-rule options
  engine.py       # walks files, builds FileContext, runs rules, collects results
  cli.py          # click commands: check, rules, config-template
  rules/
    base.py       # Rule / ProjectRule base classes + shared AST/text helpers
    <band>.py     # one module per rule family (naming.py, structure.py, ...)
    __init__.py   # ALL_RULES registry — every rule is registered here explicitly
```

There's no plugin discovery magic. A rule exists if and only if it's a class
in one of the `rules/*.py` modules **and** listed in `ALL_RULES` in
`rules/__init__.py`. That's intentional — it keeps the whole rule set
`grep`-able from one file.

Two base classes:

- **`Rule`** — sees one file at a time (`check(self, ctx: FileContext)`).
  This is what almost every rule uses.
- **`ProjectRule`** — sees every file in the run at once
  (`check_project(self, files: list[ParsedFile], config: Config)`). Only
  used where the smell is inherently cross-file, like `DP701`
  (duplicate-function-body).

## Adding a new rule

This is the most valuable kind of contribution. Walkthrough, using the shape
of a recent real one (`PY901` bare-except):

1. **Pick an ID.** IDs are `<band-prefix><number>`: `ST1xx` structure,
   `NM2xx` naming, `CM3xx` comments, `SL4xx` slicing, `TY5xx` type hints,
   `SM6xx` semantic smells, `SD8xx` SOLID, `DP7xx` duplication, `PY9xx`
   correctness. Pick the band that matches the smell and the next free
   number in it — check the table in `README.md` for what's taken.

2. **Write the `Rule` subclass** in the matching module (or a new module if
   you're starting a band). Minimal shape:

   ```python
   class BareExcept(Rule):
       id = "PY901"
       name = "bare-except"
       default_severity = Severity.WARNING
       default_options: dict = {}
       description = (
           "Flags `except:` with no exception type at all — it catches "
           "`KeyboardInterrupt` and `SystemExit` along with genuine bugs."
       )

       def check(self, ctx: FileContext) -> Iterable[Violation]:
           for handler in _except_handlers(ctx.tree):
               if handler.type is not None:
                   continue
               yield self.violation(
                   ctx,
                   handler,
                   ViolationDetails(
                       message="bare `except:` catches everything, including "
                       "KeyboardInterrupt and SystemExit",
                       suggestion="name the expected exception(s), e.g. "
                       "`except (ValueError, KeyError):`",
                       symbol=ctx.enclosing_symbol(handler),
                   ),
               )
   ```

   Every violation needs a `message` (what's wrong) and a `suggestion` (a
   concrete fix an LLM or human can act on directly — not "consider
   refactoring," an actual instruction). That's the whole point of the tool;
   see the README's "Every violation ships a fix" pitch.

3. **Register it** in `src/cleancode/rules/__init__.py`: import the class
   and add it to `ALL_RULES`.

4. **Add fixtures.** Drop a small `tests/fixtures/dirty/*.py` snippet that
   trips the rule and, if useful, a `tests/fixtures/clean/*.py` snippet that
   doesn't. `tests/test_fixtures.py` runs the whole fixture set through the
   engine as a sanity check.

5. **Write unit tests** in the matching `tests/test_<band>.py`, using the
   `check` fixture from `conftest.py`:

   ```python
   def test_flags_bare_except(self, check):
       source = (
           "def parse(raw):\n"
           "    try:\n"
           "        return int(raw)\n"
           "    except:\n"
           "        return 0\n"
       )
       assert rule_ids(check(source, "PY901")) == ["PY901"]
   ```

   `check(source, "PY901")` runs only that rule against a dedented snippet.
   Cover the positive case, the obvious near-miss that should *not* fire,
   and any documented exemption.

6. **Document it** in the rule table in `docs/RULES.md` (ID, name, default,
   severity), and add a bullet under "A few details worth knowing" if the
   rule has non-obvious exemptions or edge cases — this is where most of
   that file's existing detail comes from. Also update the category count
   in `README.md`'s "The rules" table if your rule starts a new category.

7. **Run the full loop** before opening a PR: `pytest -q`, `ruff check src
   tests`, and `clean-code check src` (the tool should stay clean on its own
   source — if your new rule flags something in `src/cleancode`, fix that
   code too, don't suppress it).

## Adding a benchmark pair

`scripts/benchmark.py` measures how much applying `clean-code`'s
suggestions actually improves a file — see the README's "How much does it
actually help?" section for the pitch. If your new rule (or a particularly
good real-world catch) deserves a before/after demonstration:

1. Drop the messy version at `tests/fixtures/benchmark/before/<name>.py`.
2. Hand-fix every violation it trips, following the rule's own `fix:`
   suggestion, and save the result at
   `tests/fixtures/benchmark/after/<name>.py`.
3. Run `python scripts/benchmark.py` and confirm the `after` file scores
   `0/0` — `tests/test_benchmark.py` enforces this in CI, so a fixture that
   still trips a violation fails the build.

Keep `before/` fixtures realistic (the kind of thing an LLM actually
produces) rather than synthetic worst cases built to maximize the score.

## Fixing an existing rule

Same test discipline: add a regression test that fails before your fix and
passes after, in the relevant `tests/test_<band>.py`. If the bug is a false
positive/negative on a specific real-world shape, prefer reproducing that
shape in the test over a synthetic one.

## Commit messages

This repo's history uses a light convention worth following:
`*ADD* <what>`, `*FIX* <what>`, `*DELETE* <what>` — short, imperative,
one line. Not enforced, but keeps `git log` scannable.

## Opening a PR

- Keep PRs scoped to one rule or one fix — easier to review, easier to
  revert if a rule turns out too noisy in practice.
- Fill in the PR template; it mirrors this checklist.
- If you're proposing a new rule *idea* without an implementation yet, open
  an issue with the "new rule" template instead — happy to discuss the
  shape before code gets written.
