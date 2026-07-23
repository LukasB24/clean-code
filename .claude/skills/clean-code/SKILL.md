---
name: clean-code
description: Enforce human-readable Python with the cleancode analyzer plus a judgment-tier review. Use this to check existing files, or to generate new code that is minimal, well-named, and free of unnecessary boilerplate.
arguments:
  type: object
  properties:
    target_path:
      type: string
      description: The path to the Python file or directory to check.
    instruction:
      type: string
      description: Instruction for generating a new Python file if target_path is not provided.
  required: []
---

# Clean Code

Clean code has two tiers, and they need two different mechanisms:

- **Mechanical tier** — short names, magic numbers, nesting, bare `except`,
  comments that restate code. These have fixed shapes, so the deterministic
  `clean-code` analyzer catches them for free, the same way every time.
- **Judgment tier** — is this abstraction *necessary*? Is the solution
  *proportionate to the problem*? Does this comment *earn its place*? An AST
  can't answer these; they only mean something relative to what was asked.

This skill enforces both, and prevents the judgment-tier problems at generation
time rather than only catching them afterward.

## If `target_path` is provided (check existing code)

1. Run `clean-code check "{{target_path}}"`. If the summary says violations are
   hidden below `--min-severity warning` and a deeper pass is wanted, rerun with
   `--min-severity info`.
2. Fix each violation directly using its suggested `fix:` pattern. Do not silence
   violations with inline `# cleancode: disable` comments unless the user asks.
3. `DP701` / `SD801` / `SD802` are SOLID/DRY smells, not one-line nits — the fix
   (extract a shared helper, replace a type-switch with polymorphism or a
   dispatch table, split a class) usually means new functions/classes and changed
   call sites. Apply the refactor and summarize what you restructured and why.
   `DP701` compares functions across every file in one `check` run, so prefer
   checking the containing directory when hunting cross-file duplication.
4. **Optional deep pass:** to also audit for unnecessary boilerplate and
   over-complication, run the Clean-Code Judge (see
   `references/clean-code-judge.md`) — you'll need the code's intent to do this.

## If an `instruction` is provided (generate new code)

Drive the full five-phase loop. Do **not** skip straight to generating.

**Phase 0 — Constrain.** Read `references/minimalism-constitution.md` and hold
its defaults while you write. The goal is that bloat is never generated, not that
it is caught later.

**Phase 1 — Generate.** Write the smallest code that fully satisfies the
instruction, plus tests that pin the required behavior. Save it to a temporary
path (`{{generated_file_path}}`).

**Phase 2 — Mechanical floor.** Run
`clean-code check --min-severity info "{{generated_file_path}}"` and fix every
finding using its `fix:` pattern (same handling as the check-existing-code
section above). This is cheap, so it runs before the judgment pass.

**Phase 3 — Judge.** Run the Clean-Code Judge (see
`references/clean-code-judge.md`) as a fresh subagent, giving it the original
instruction, the code, the tests, and the mechanical findings you already fixed.
It reviews only the judgment tier — necessity, simplicity, comment value — and
returns line-cited `DELETE` / `SIMPLIFY` / `INLINE` findings.

**Phase 4 — Revise.** Apply the judge's findings, then **re-run the tests and
`clean-code check`**. Revert any change that breaks a test. Cap at two judge
rounds; apply the safe findings and note the rest rather than thrashing.

**Phase 5 — Report.** Present the final code, confirm the tests pass and the
analyzer is clean, and include a one-paragraph **deletion summary**: what you
removed or simplified and why. That summary is where the judgment tier shows its
work — if you consciously kept something the Constitution defaults against, say
why here.
