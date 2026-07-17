---
name: clean-code
description: Enforce human-readable Python with the cleancode analyzer. Use this to check existing files or to generate and validate new code based on instructions.
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

# Clean Code Analyzer

Run the `clean-code` static analyzer on the targeted Python file or directory to enforce formatting, structure, and readability standards. The workflow has three stages: **prime** before writing, **check** after, **fix** until clean.

### Workflow

1. **Prime, before writing any Python.** Run `clean-code guide "{{target_path or the directory you're working in}}"` and follow its instructions while you write — it's a short brief rendered from the project's own config, so it reflects the actual thresholds you'll be checked against. Do this whether `target_path` or `instruction` was given; if only an `instruction` was given, run it against the directory the generated file will live in (or `.` if none is obvious).

2. **Generate or locate the code:**
   * **If `target_path` is provided:** that's the code to check — skip to step 3.
   * **If no `target_path` is provided but an `instruction` is:** generate the requested Python code, following the primed guidance, and save it to a temporary path (`{{generated_file_path}}`).

3. **Check:**
   Execute: `clean-code check "{{target_path or generated_file_path}}"`
   * `DP701` (cross-file duplication) only sees duplicates across every file reached in one `check` run — prefer checking the containing directory (or the whole project) when hunting for it, not just the one file you touched.

4. **Fix, iterating until clean:**
   * By default, `info`-severity violations (the fuzziest, lowest-signal rules) are hidden to avoid context noise. If the summary indicates violations hidden below `--min-severity warning` and a deeper pass is warranted, rerun with `clean-code check --min-severity info "{{target_path}}"`.
   * Apply the suggested `fix:` pattern for each violation directly in the source.
   * `DP701`/`DP702`/`SD801`/`SD802` findings are SOLID/DRY smells, not local style nits — the `fix:` suggestion (extract a shared helper, replace a type-switch with polymorphism/a dispatch table, split a class) usually means introducing a new function/class or changing call sites, not a one-line edit. Apply the refactor, but summarize what you restructured and why when presenting the result, since these findings reshape the code's structure more than the other rules do.
   * Re-run `clean-code check` after each round of fixes.
   * **Stop conditions:** stop as soon as `check` exits clean, or after 3 fix iterations — whichever comes first. If violations remain after 3 iterations (including a fix for one rule that keeps re-triggering another), stop, present the remaining violations verbatim to the user along with a short note on the tension, and do not suppress them to force a clean exit.
   * Do not silence violations using inline `# cleancode: disable` comments unless the user specifically asks for it.

5. **Present the final cleaned code back to the user**, along with a summary of any structural refactors from step 4.
