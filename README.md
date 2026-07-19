<p align="center">
  <img src="https://raw.githubusercontent.com/LukasB24/clean-code/main/assets/clean-code_banner.gif" alt="clean-code: a messy LLM-generated function on the left becomes a short, well-named function on the right" width="700">
</p>

<h1 align="center">clean-code</h1>

<p align="center">
  <strong>Your agent solved the hard problem. The code never explains how.<br>
  clean-code does that part — deterministically, so the next person to read it can tell.</strong>
</p>

<p align="center">
  <a href="https://github.com/LukasB24/clean-code/actions/workflows/ci.yml"><img src="https://github.com/LukasB24/clean-code/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/clean-code/"><img src="https://img.shields.io/pypi/v/clean-code.svg" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <img src="https://img.shields.io/badge/deps-click_only-informational.svg" alt="Only dependency: click">
  <img src="https://img.shields.io/badge/analysis-deterministic-informational.svg" alt="No LLM calls, no API key">
</p>

---

Agents get the hard logic right. They don't make it easy to follow — deep
nesting, terse names, comments that just restate the code. It works -
nobody understands why.

clean-code closes that gap. Two things make it different from asking an LLM
to review its own code:

- **Finding violations is deterministic and needs no API key.** Every rule
  but one is plain `ast` parsing — same input, same output, every time, and
  every result traces back to the exact rule that raised it. The one
  exception, `CM307`, scores a docstring/comment against a small, frozen
  classifier that's trained offline and checked into the package (see
  [`docs/RULES.md`](docs/RULES.md#a-few-details-worth-knowing)) — no LLM
  call, no network access, and its output is just as reproducible as every
  other rule's: the same clause always scores the same.
- **Every violation comes with an actual fix.** Instead of a vague "too
  complex," you get a specific instruction — rename this, extract that,
  flatten this branch — that you, or the agent that wrote the code, can act
  on right away.

## Install

```bash
pip install clean-code
```

That's it — you get a `clean-code` command. Requires Python 3.11+, and the
only dependency is `click`.

Working on clean-code itself? See [`CONTRIBUTING.md`](CONTRIBUTING.md) for
an editable install (`pip install -e ".[dev]"`).

## Quickstart

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

Then trigger it directly within your Claude Code CLI or VS Code extension:

```text
/clean-code [instruction or target_path]
```

## See it catch something real

Given `checkout.py`, fresh out of an LLM:

```python
def calc(u, o):
    if u.active:
        if o.total > 500:
            discount = o.total * 0.15
        else:
            discount = o.total * 0.05
    try:
        charge(o, o.total - discount)
    except:
        pass
    return discount
```

```text
$ clean-code check checkout.py
checkout.py:
  1:9: warning NM201 short parameter `u` (1 characters)
      fix: use a descriptive name that states what the value represents
  1:12: warning NM201 short parameter `o` (1 characters)
      fix: use a descriptive name that states what the value represents
  3:21: warning SM607 magic number `500` — extract it to a named, typed constant
      fix: e.g. `SOME_DESCRIPTIVE_NAME = 500`
  4:33: warning SM607 magic number `0.15` — extract it to a named, typed constant
      fix: e.g. `SOME_DESCRIPTIVE_NAME = 0.15`
  6:33: warning SM607 magic number `0.05` — extract it to a named, typed constant
      fix: e.g. `SOME_DESCRIPTIVE_NAME = 0.05`
  9:4: warning PY901 bare `except:` catches everything, including KeyboardInterrupt and SystemExit
      fix: name the expected exception(s), e.g. `except (ValueError, KeyError):`
  9:4: warning PY902 exception silently discarded — handler body does nothing to acknowledge the failure
      fix: log it, return an explicit fallback, or re-raise — anything that leaves a trace

7 violation(s) in 1 file(s): 0 error(s), 7 warning(s), 0 info(s)
```

Nothing exotic — a couple of one-letter parameters, some magic numbers, and
a swallowed exception. Exactly the kind of thing that slips through a quick
glance at an LLM's output, and exactly what clean-code is for.

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

## Prime your agent: `clean-code guide`

`clean-code check` is a *reactive* loop — it finds what's already wrong.
`clean-code guide` is the other half: a short, generation-time brief that
turns every enabled rule into a "write it this way" instruction, so an LLM
can follow the rules while it writes instead of fixing them after:

```bash
clean-code guide src
```

It's rendered from your project's own config, so a loosened `max_depth` or
a disabled rule shows up correctly — no drift between what the brief says
and what `check` actually enforces. Feed it to an agent before it generates
code, or append it once to your project's `CLAUDE.md`/`AGENTS.md`:

```bash
clean-code guide --agents-md >> CLAUDE.md
```

If a violation from `check` isn't self-explanatory, `clean-code explain
<RULE_ID>` prints the rule's full description, its guidance line, and a
minimal BAD/GOOD before/after example to pattern-match against:

```bash
clean-code explain SM607
```

## Configure it for your project

Out of the box the defaults are strict (max nesting depth 2, max 3
function params, etc.) — good for shaking out problems, but you'll likely
want to loosen a few knobs for your codebase. Drop a `[tool.cleancode]` table
in your `pyproject.toml`:

```toml
[tool.cleancode]
disable = ["NM203"]           # rules you don't want at all
fail_on = "warning"           # info | warning | error — what fails the build
exclude = ["migrations/**"]   # globs to skip, relative to this file's directory

[tool.cleancode.ST101]
max_depth = 3                 # loosen the default nesting limit

[tool.cleancode.NM201]
allowed = ["i", "j", "k", "n", "x", "y", "_", "id", "ok", "fh", "df"]  # your short names are fine
```

clean-code finds this automatically by walking up from whatever path you
check (or point it elsewhere with `--config`).

One line too noisy to fix right now? Suppress it inline instead of touching
the config — or, when the line has no room for a trailing comment, put the
directive on its own line directly above:

```python
legacy_tmp = migrate(rows)  # cleancode: disable=NM202

# cleancode: disable=SM607
retry_delay_seconds = base_delay * 1.5
```

## The rules

51 rules across 9 categories, each with a default severity you can override:

| Category | IDs | Count | Catches |
|----------|-----|-------|---------|
| Structure | ST101–ST109 | 9 | nesting, length, params, complexity, mixed responsibilities, oversized modules, redundant `else` |
| Naming | NM201–NM203 | 3 | single-letter names, `data`/`tmp`/`process_data`, cryptic abbreviations |
| Comments & docstrings | CM301–CM306 | 6 | docstrings/comments that just restate the code, comment-heavy files, banner comments |
| Subscripts | SL401–SL402 | 2 | `x[i][j][k]`-style complexity and chaining |
| Types | TY501 | 1 | uninformative `Any` |
| Structural smells | SM601–SM622 | 22 | magic numbers, nested comprehensions, redundant ternaries, PyTorch pitfalls, unused bindings, builtin shadowing, nested ternaries, callable indirection, deep expressions, thin wrappers, buried fallbacks, returned temporaries, compatibility aliases, trivial property pairs, and more |
| SOLID | SD801–SD803 | 3 | type-switches violating OCP, low-cohesion classes, all-static namespace classes |
| Duplication | DP701–DP702 | 2 | copy-pasted and exactly-duplicated function bodies |
| Correctness | PY901–PY903 | 3 | bare `except:`, silently-discarded exceptions, oversized broad-except `try` blocks |

`cleancode rules` prints the full list from the CLI. For every rule's exact
default options, severity, and the edge cases each one accounts for (what's
exempt and why), see **[docs/RULES.md](docs/RULES.md)**.

## Disclaimer

The software is provided "as is", without warranty of any kind, express or
implied, including but not limited to the warranties of merchantability,
fitness for a particular purpose, completeness, or correctness. In no event
shall the authors be liable for any claim, damages, or other liability
arising from the use of this software.

## Contributing

Bug reports, new rule proposals, and PRs are welcome — see
[`CONTRIBUTING.md`](CONTRIBUTING.md) for the dev setup and a walkthrough of
adding a rule, [`CHANGELOG.md`](CHANGELOG.md) for what's shipped, and
[`RELEASING.md`](RELEASING.md) for how versions get published.

## License

[Apache 2.0](LICENSE). See [`NOTICE`](NOTICE) for a third-party asset
(CM307's vendored, Llama-2-derived embedding table) that is licensed
separately.
