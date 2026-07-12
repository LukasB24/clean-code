# clean-code

**A readability enforcer for LLM-generated Python.**

LLM-generated code usually *works* — but a human still has to review it. And what
LLMs produce is often exactly what makes review painful: five levels of nested
loops and `if`s, 80-line functions, names like `data2` and `do_stuff`, subscript
one-liners like `x[:, None, idx[i+1]:idx[i+2]:2, ::-1]`, and a blanket of
docstrings and comments that restate the code without saying anything.

clean-code enforces reviewable Python by utilizing a **static analyzer** (`cleancode check`) — 17 deterministic rules built on
   stdlib `ast` + `tokenize`, tuned for the failure modes of generated code.
   No LLM is needed to *check* code.

## Disclaimer

This project is under active development. The software is provided "as is", 
without warranty of any kind, express or implied, including but not limited 
to the warranties of merchantability, fitness for a particular purpose, 
completeness, or correctness. In no event shall the authors be liable for 
any claim, damages, or other liability arising from the use of this software.

## Installation

```bash
pip install -e .
pytest
clean-code check src
```

Requires Python ≥ 3.11. The core has a single dependency (`click`).

## Use as a Claude Code skill

This repo ships a [Claude Code](https://claude.com/claude-code) skill at
`.claude/skills/clean-code/`. To make it available in every session, copy it to
your user skills folder:

```bash
mkdir -p ~/.claude/skills/ && cp -r .claude/skills/clean-code ~/.claude/skills/
```

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
trades.py:1:0: warning NM202 [meaningless-name] meaningless function name `process_data`
trades.py:1:17: warning NM202 [meaningless-name] meaningless parameter name `data`
trades.py:2:4: warning CM301 [docstring-restates-name] docstring of `process_data` only restates the function signature
trades.py:3:4: warning NM202 [meaningless-name] meaningless variable name `result`
trades.py:6:12: error ST101 [max-nesting-depth] nesting depth 5 exceeds the maximum of 2
trades.py:9:24: warning CM302 [comment-restates-code] comment restates the code it annotates: `# append the price to result`

6 violation(s) in 1 file(s): 1 error(s), 5 warning(s), 0 info(s)
```

Every violation carries a concrete fix suggestion (shown with `fix:` in the
output).

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

## Configuration

Add a `[tool.cleancode]` table to your `pyproject.toml` (found automatically by
walking up from the checked path, or pass `--config`):

```toml
[tool.cleancode]
disable = ["NM203"]
fail_on = "warning"          # info | warning | error
exclude = ["migrations/**"]

[tool.cleancode.ST101]
max_depth = 3

[tool.cleancode.NM201]
allowed = ["i", "j", "k", "n", "x", "y", "_", "df"]

[tool.cleancode.CM303]
severity = "warning"
```

Unknown rule ids or option keys are rejected loudly, so typos can't silently
disable a rule.

Suppress a single line with an inline comment, and audit suppressions with
`--no-suppress`:

```python
legacy_tmp = migrate(rows)  # cleancode: disable=NM202
```

CLI extras: `--select ST101,CM302` runs only those rules, `--ignore` skips
rules, `--json` emits machine-readable output. Exit codes: `0` clean, `1`
violations at or above `fail_on`, `2` usage or syntax error.

## Python API

```python
from cleancode import analyze_source, Config

result = analyze_source(open("trades.py").read())
for violation in result.violations:
    print(violation.rule_id, violation.line, violation.message)
```

## Design notes

- Analysis is pure stdlib (`ast` for structure, `tokenize` for comments —
  `ast` discards them). One parse per file; each rule is an independent,
  self-contained visitor.
- The heuristics are deliberately deterministic and tunable: word-overlap
  thresholds, stop-word/synonym tables, and ban lists live in one place and in
  config, and every fuzzy rule (NM203, CM303) defaults to `info` severity.
- The project dogfoods itself: the test suite fails if `cleancode check src/`
  reports anything.
