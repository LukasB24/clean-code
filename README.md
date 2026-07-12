# clean-code

You ask an LLM for a function and it hands back something that runs — buried
five `if`s deep, 90 lines long, with a variable called `data2` and a comment
that just repeats the line under it. It works. Nobody wants to review it.

clean-code is a linter built for exactly that mess. Two things make it
different from asking an LLM to review its own code:

- **Finding violations costs nothing and never hallucinates.** It's plain
  `ast` parsing under the hood, not another model — deterministic, instant,
  and reproducible. No API key, no tokens burned, no judgment call you can't
  trace back to a rule.
- **Every violation ships a fix an LLM can act on directly.** Not just "line
  12: too complex," but a concrete instruction — rename this, extract that,
  flatten this branch — so you (or the agent that wrote the code) can feed
  the output straight back in and get a real correction, not another guess.

## Disclaimer

This project is under active development. The software is provided "as is",
without warranty of any kind, express or implied, including but not limited
to the warranties of merchantability, fitness for a particular purpose,
completeness, or correctness. In no event shall the authors be liable for
any claim, damages, or other liability arising from the use of this software.

## Install

```bash
pip install -e .
```

That's it — you get a `clean-code` command. Requires Python 3.11+, and the
only dependency is `click`.

Point it at your code:

```bash
clean-code check src
```

### Using it with Claude Code

If you want clean-code to run itself as part of a Claude Code session, copy
the bundled skill into your user skills folder once:

```bash
mkdir -p ~/.claude/skills/ && cp -r .claude/skills/clean-code ~/.claude/skills/
```

### Usage

Once installed, trigger the tool directly within your Claude Code CLI or VS Code extension:

```text
/clean-code [instruction or target_path]
```

## Set it up for your project

Out of the box the defaults are strict (max nesting depth 2, max 3
function params, etc.) — good for shaking out problems, but you'll likely
want to loosen a few knobs for your codebase. Drop a `[tool.cleancode]` table
in your `pyproject.toml`:

```toml
[tool.cleancode]
disable = ["NM203"]           # rules you don't want at all
fail_on = "warning"           # info | warning | error — what fails the build
exclude = ["migrations/**"]   # globs to skip entirely

[tool.cleancode.ST101]
max_depth = 3                 # loosen the default nesting limit

[tool.cleancode.NM201]
allowed = ["i", "j", "k", "n", "x", "y", "_", "id", "ok", "fh", "df"]  # your short names are fine
```

clean-code finds this automatically by walking up from whatever path you
check (or point it elsewhere with `--config`).

One line too noisy to fix right now? Suppress it inline instead of touching
the config:

```python
legacy_tmp = migrate(rows)  # cleancode: disable=NM202
```

That's the whole setup. Everything below is reference material — the demo
and the full rule list — for when you need it.

## 30-second demo

Given `trades.py`, fresh out of an LLM:

```python
def process_data(data):
    """Process the data."""
    result = []
    for item in data:
        if item is not None:
            if item.symbol:
                if item.qty > 0:
                    for x in range(item.qty):
                        # append the price to result
                        result.append(item.price)
    return result
```

```text
$ cleancode check trades.py
trades.py:
  1:0: warning NM202 meaningless function name `process_data`
      fix: rename to describe the content or role, e.g. `raw_rows`, `user_totals`, `parse_trades`
  1:17: warning NM202 meaningless parameter name `data`
      fix: rename to describe the content or role, e.g. `raw_rows`, `user_totals`, `parse_trades`
  2:4: warning CM301 docstring of `process_data` only restates the function signature
      fix: delete it, or document what the name cannot say: why, edge cases, units, invariants
  3:4: warning NM202 meaningless variable name `result`
      fix: rename to describe the content or role, e.g. `raw_rows`, `user_totals`, `parse_trades`
  6:12: error ST101 nesting depth 5 exceeds the maximum of 2
      fix: extract the inner block into a well-named helper function, or flatten with early returns / guard clauses
  9:24: warning CM302 comment restates the code it annotates: `# append the price to result`
      fix: delete it; comments should explain *why*, not repeat *what*

6 violation(s) in 1 file(s): 1 error(s), 5 warning(s), 0 info(s)
```

Violations are grouped by file (the path is printed once, not repeated per
line) and each carries a concrete fix suggestion — both cut tokens when the
tool is driven by an LLM. The `rule_name` is still available via `--json` or
`cleancode rules`, just not repeated inline since the message already says
what the rule name would.

By default `info`-severity violations (the fuzziest, lowest-signal rules) are
hidden — pass `--min-severity info` to see everything. `--min-severity` never
hides a violation that `--fail-on`/`fail_on` would fail the run on: setting
`fail_on` without `min_severity` lowers the display floor to match, so you
always see what can fail your build. Set `min_severity` explicitly to
override that.

## The rules

| ID | Name | Default | Severity |
|----|------|---------|----------|
| ST101 | max-nesting-depth | `max_depth=2` | error |
| ST102 | max-function-length | `max_lines=60` | warning |
| ST103 | max-class-length | `max_lines=200` | warning |
| ST104 | max-parameters | `max_params=3` | warning |
| ST105 | max-complexity | `max_complexity=10` | error |
| ST106 | do-one-thing | `conjunctions=[and, or]` | warning |
| ST107 | too-many-guard-clauses | `max_guards=2` | info |
| NM201 | short-name | `min_length=3, allowed=[i,j,k,n,x,y,_,id,ok,fh]` | warning |
| NM202 | meaningless-name | configurable ban lists | warning |
| NM203 | cryptic-abbreviation | `known_abbrevs=[cfg,ctx,idx,…]` | info |
| CM301 | docstring-restates-name | `overlap=0.8` | warning |
| CM302 | comment-restates-code | `overlap=0.7, min_words=2` | warning |
| CM303 | comment-density | `max_ratio=0.3, min_code_lines=5` | info |
| CM304 | boilerplate-param-docs | `min_uninformative=0.5` | warning |
| SL401 | complex-subscript | `max_score=5` | warning |
| SL402 | chained-subscript | `max_chain=2` | warning |
| TY501 | uninformative-any | — | warning |
| SM601 | comprehension-density | — | warning |
| SM602 | anonymous-tuple-indexing | — | warning |
| SM603 | magic-string-branching | — | warning |
| SM604 | redundant-boolean-ternary | — | warning |
| SM605 | reduce-instead-of-sum | — | warning |
| SM606 | repeated-collection-iteration | — | warning |
| SM607 | magic-number | `ignore=[0,1,-1,2,10]` | warning |
| SM608 | non-idiomatic-emptiness-check | — | warning |
| SM609 | eager-dataset-loading | — | warning |
| SM610 | premature-device-placement | — | warning |
| SM611 | redundant-isinstance-check | — | warning |

`cleancode rules` prints the same list with full descriptions.

A few details worth knowing:

- **Naming rules look at binding sites only** (assignments, defs, parameters,
  loop targets) — a bad name is reported once, where it is introduced.
  `i`/`x` are fine as loop, comprehension, and lambda targets; `except ... as e`
  is fine; `T = TypeVar("T")` and `ALL_CAPS` constants are exempt.
- **NM201 flags names under `min_length` characters**, not just single
  letters — `ab`, `bc`, and `df` are cryptic even though they're not bare
  letters. Single-character names keep the old loop/comprehension/lambda-only
  exemption; short multi-letter names (`id`, `ok`, `fh`, ...) are exempt via
  the same `allowed` list regardless of where they're bound.
- **CM301/CM302 are deterministic**, not LLM-judged: they compare the
  informative words of a docstring/comment against the identifier words (plus
  an operator-synonym table) of the code it annotates. `x = x + 1  # increment
  x by 1` is flagged; a comment explaining *why* is not. Generic filler nouns
  ("number", "value", "variable", ...) are ignored on the comment side so they
  can't dilute the overlap score — `x += 1  # increase a number` is flagged.
  `TODO`/`FIXME`/`NOTE` and tool directives are always exempt.
- **SL401 scores subscripts** (+1 per dimension, step, `None`/`...`, negative
  index, arithmetic, or call in the index; +2 per nested subscript; negative
  steps count double) and ignores type annotations like `dict[str, int]`.
- **SM6xx catches structural smells that node-counting misses**: SM601 flags
  a comprehension nesting another comprehension whose filter is a ternary;
  SM602 flags integer-constant indexing (`bounds[0]`) into a parameter typed
  as a fixed multi-element tuple (`tuple[T, ...]` variadic tuples are exempt);
  SM603 flags inline ternaries whose branch is chosen by a hardcoded
  `.startswith()`/`.endswith()`/`.find()`/`.rfind()` string check — plain
  `if`/`elif` statements using the same methods are not flagged, since that's
  ordinary, idiomatic control flow. SM604 flags ternaries that return
  explicit `True`/`False` literals for an already-boolean condition; SM605
  flags `reduce(lambda a, b: a + b, xs)` in favor of `sum(xs)`; SM606 flags a
  comprehension re-iterating a `Subscript`/`Attribute`/`Call` collection
  (`item["metrics"]`) already iterated earlier in the same function — bare
  variable names are exempt, since consuming an already-computed local in a
  second comprehension is an ordinary filter-then-map step, not a repeated
  pass over a shared source; SM607 flags numeric literals embedded directly
  in a `BinOp`/`Compare` (not literals assigned straight to a name), exempting
  a configurable `ignore` list; SM608 flags `len(x) > 0`/`len(x) == 0` style
  checks in favor of `if x:`/`if not x:`. SM609/SM610 target
  `torch.utils.data.Dataset` subclasses (matched syntactically by base-class
  name, no type checker involved): SM609 flags file/array-loading calls
  (`np.load`, `open`, `Image.open`, `cv2.imread`, `torch.load`) inside
  `__init__` — eager loading of every sample defeats lazy loading and can OOM;
  SM610 flags `.cuda()`/`.to(device=...)` calls inside `__init__` or
  `__getitem__` — initializing a CUDA context before `DataLoader` workers fork
  corrupts it across worker processes. SM611 flags `isinstance(x, T)` where
  `x` already carries a simple (non-generic) static annotation of exactly
  `T` — the check is hallucinated safety a type checker already guarantees.
- `elif` chains do **not** count as nesting for ST101 (each branch still counts
  toward ST105 complexity).
