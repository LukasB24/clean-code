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
allowed = ["i", "j", "k", "n", "x", "y", "_", "df"]  # your short names are fine
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
| NM201 | single-letter-name | `allowed=[i,j,k,n,x,y,_]` | warning |
| NM202 | meaningless-name | configurable ban lists | warning |
| NM203 | cryptic-abbreviation | `known_abbrevs=[cfg,ctx,idx,…]` | info |
| CM301 | docstring-restates-name | `overlap=0.8` | warning |
| CM302 | comment-restates-code | `overlap=0.7, min_words=2` | warning |
| CM303 | comment-density | `max_ratio=0.3, min_code_lines=5` | info |
| CM304 | boilerplate-param-docs | `min_uninformative=0.5` | warning |
| SL401 | complex-subscript | `max_score=5` | warning |
| SL402 | chained-subscript | `max_chain=2` | warning |
| TY501 | uninformative-any | — | warning |

`cleancode rules` prints the same list with full descriptions.

A few details worth knowing:

- **Naming rules look at binding sites only** (assignments, defs, parameters,
  loop targets) — a bad name is reported once, where it is introduced.
  `i`/`x` are fine as loop, comprehension, and lambda targets; `except ... as e`
  is fine; `T = TypeVar("T")` and `ALL_CAPS` constants are exempt.
- **CM301/CM302 are deterministic**, not LLM-judged: they compare the
  informative words of a docstring/comment against the identifier words (plus
  an operator-synonym table) of the code it annotates. `x = x + 1  # increment
  x by 1` is flagged; a comment explaining *why* is not. `TODO`/`FIXME`/`NOTE`
  and tool directives are always exempt.
- **SL401 scores subscripts** (+1 per dimension, step, `None`/`...`, negative
  index, arithmetic, or call in the index; +2 per nested subscript; negative
  steps count double) and ignores type annotations like `dict[str, int]`.
- `elif` chains do **not** count as nesting for ST101 (each branch still counts
  toward ST105 complexity).
