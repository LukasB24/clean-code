---
name: New rule proposal
about: Propose a readability/correctness smell clean-code should catch
title: "New rule: "
labels: new-rule
---

**The smell**

Describe the pattern in LLM-generated (or any) Python that this would catch.
A short before/after snippet is the clearest way to show it:

```python
# before: what trips the rule
```

```python
# after: what the fix suggestion should push toward
```

**Why it matters**

Why is this worth a dedicated rule rather than being covered by an existing
one (check the table in `README.md` first)? What makes the "before" version
harder to read or more error-prone than the "after"?

**Suggested band and severity**

Which existing band does this fit (`ST1xx` structure, `NM2xx` naming,
`CM3xx` comments, `SL4xx` slicing, `TY5xx` type hints, `SM6xx` semantic
smells, `SD8xx` SOLID, `DP7xx` duplication, `PY9xx` correctness) or does it
need a new one? Info / warning / error?

**Known false positives**

Any legitimate code shape that looks like the smell but isn't. Rules that
ship without thinking about this tend to get disabled by users instead of
fixed — see the README's "A few details worth knowing" section for the
level of care expected here.

**Willing to implement it?**

If yes, see `CONTRIBUTING.md` for the walkthrough — happy to review a PR
directly instead of designing it here first.
