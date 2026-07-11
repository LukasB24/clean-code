---
name: cleancode
description: >-
  Enforce human-readable Python with the cleancode analyzer. Use this whenever
  you write or edit Python source (functions, modules, scripts) to catch the
  readability problems LLM-generated code is prone to — deep nesting, oversized
  functions, too many parameters, cryptic or meaningless names, docstrings and
  comments that just restate the code, over-complex array/tensor slicing, and
  uninformative `Any` type hints — and fix them before presenting the code as
  done. Triggers: "clean up this code", "make this readable", "check my Python",
  "is this reviewable", or any task that produces non-trivial Python.
---

# CleanCode

`cleancode` is a static analyzer that flags the ways generated Python becomes
hard for a human to review, and can also drive an LLM to (re)generate code that
passes those checks. Use it as a gate on Python you produce.

## When to use it

Run `cleancode check` on any Python file you create or meaningfully edit, before
you consider the work finished. Treat an error-severity finding (e.g. deep
nesting) as a must-fix; treat warnings as fix-by-default unless the user opted
out via config.

## Setup (once per environment)

```bash
pip install -e .        # from this repo, or: pip install cleancode
```

## Checking existing code

```bash
cleancode check path/to/file.py          # or a directory
cleancode check --json path/              # machine-readable
```

Each finding includes a `fix:` suggestion. Apply the fix (extract a helper to
cut nesting, rename `data2`/`tmp`, delete a comment that restates the code,
name intermediate slice variables, replace bare `Any` with a `TypedDict`,
dataclass, or `object`), then re-run until the file is clean.

Do **not** silence findings with `# cleancode: disable=...` unless the user
asks — fix the underlying issue instead.

## Generating clean code from a prompt

```bash
cleancode generate "parse a CSV of trades and return per-symbol totals" --out trades.py
cleancode generate "..." --via claude-code   # reuse the logged-in claude CLI, no API key
```

The loop generates, checks, feeds violations back, and re-generates until the
result passes every rule or the iteration budget is spent.

## Reference

- `cleancode rules` — list every rule, its default threshold, and severity.
- `cleancode config-template` — print a commented config listing every rule and
  option; copy what you need into `pyproject.toml` under `[tool.cleancode]`.

## Installing this skill globally

Copy this folder to your user skills directory so it is available in every
Claude Code session, not just this repo:

```bash
cp -r .claude/skills/cleancode ~/.claude/skills/cleancode
```
