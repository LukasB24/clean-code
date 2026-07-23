# The Clean-Code Judge

The deterministic analyzer owns the **mechanical tier**: naming (`NM`), magic
numbers and structural smells (`SM`), comment *restatement* (`CM`), nesting and
length (`ST`), correctness (`PY`), and the rest. Run it first and fix everything
it reports.

The Judge owns the **judgment tier** — the qualities an AST cannot see because
they only have meaning relative to *what was asked*:

- **Boilerplate** the analyzer accepts because it is structurally valid.
- **Comments and docstrings** that are not redundant per `CM301/302` but still
  earn nothing.
- **Over-complication** — a solution heavier than the problem needs.

## How to run it

Run the Judge as a **fresh subagent** (the Agent / Task tool), not inline. The
reviewer must have **no authorship attachment** to the code — it is reviewing
code it did not write, against the spec that code was supposed to satisfy.

Hand the subagent exactly this context:

1. **The original instruction / spec** — the problem the code was asked to solve.
   Every "unnecessary" and "over-built" verdict is measured against *this*, not
   against an abstract ideal.
2. **The code**, with line numbers.
3. **The tests** — these are ground truth. A proposed deletion or simplification
   is only valid if the tests still pass afterward.
4. **The deterministic findings already fixed** — so the Judge does not
   re-litigate them.

## The Judge's instructions (give these verbatim to the subagent)

> You are a senior engineer reviewing code you did not write, against the spec
> it was meant to satisfy. Your job is **subtraction**, not praise.
>
> Assume every abstraction, helper, class, parameter, comment, and docstring is
> **guilty until justified**. For each one, either give a one-line justification
> tied to the spec or the tests, or mark it `DELETE` / `SIMPLIFY` with a
> concrete, line-cited instruction for how.
>
> You do **not** review naming, magic numbers, nesting, or comment-restates-code
> — a deterministic analyzer already owns those. Do not repeat them.
>
> Score each rubric dimension, then output findings. A finding is only valid if
> applying it keeps the tests passing.

### Rubric

Score each dimension **pass** or **revise**. A `revise` must carry at least one
line-cited, actionable finding.

1. **Necessity** (highest weight) — Does every function, class, parameter, and
   abstraction earn its place against the spec? Flag: single-implementation
   interfaces, factories/wrappers for one use, config objects with one call
   site, "for future use" code, dead branches, unused generality.
2. **Simplicity vs. the problem** (high weight) — Is the solution proportionate
   to the instruction? Ask: *could a senior engineer deliver the same behavior
   with materially less code or structure?* If yes, describe the smaller shape.
3. **Comment & docstring value** (medium weight) — Does each comment/docstring
   carry information not already in the code? (This is *beyond* `CM301/302`,
   which only catch restatement — you catch the ones that are technically
   non-redundant but still worthless, and the sheer *volume* of unearned prose.)
4. **Clarity of intent** (lowest weight) — Does the code read as the story of the
   problem? Only raise this when it points at a concrete restructuring, never as
   a vibe.

### Output format (every finding mirrors the analyzer's "fix" contract)

```
DIMENSION: <name>  VERDICT: <pass|revise>
  <file>:<line-range>  <DELETE|SIMPLIFY|INLINE>  <what>
      why: <one line, tied to the spec or tests>
      how: <the concrete edit>
```

End with a single line: `VERDICT: accept` or `VERDICT: revise (<n> findings)`.

## Applying the result

- Apply each `DELETE`/`SIMPLIFY`/`INLINE`, then **re-run the tests and
  `clean-code check`**. Revert any change that breaks a test; a simplification
  that loses required behavior is not a simplification.
- **Bounded iterations:** at most **2** Judge rounds. If the second round still
  returns findings, apply the safe ones, note the rest in the report, and stop —
  do not thrash.
- Carry the surviving findings into the Phase 5 deletion summary.
