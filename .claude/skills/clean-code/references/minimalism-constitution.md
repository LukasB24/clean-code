# The Minimalism Constitution

Load this **before writing a single line** of generated code. These are the
defaults you generate under. Each one is a hard default: you may override it,
but only deliberately, and the Phase 5 report must say why.

The deterministic analyzer (`clean-code check`) already guards the *mechanical*
tier — short names, magic numbers, nesting, bare `except`, comments that restate
code. It cannot see whether code is **necessary**, **proportionate to the
problem**, or **worth its comments**. That is what this Constitution prevents at
the source, so the analyzer and the judge have less to clean up later.

## The one rule everything else serves

> Write the smallest code that fully satisfies the instruction and its tests —
> and nothing the instruction did not ask for.

"Smallest" means fewest concepts a reader must hold in their head, not fewest
characters. Do not code-golf. Do not sacrifice clarity for brevity.

## The defaults

### 1. Comments and docstrings must earn their place
- No docstring or comment unless it adds information that the name, signature,
  and type hints do not already carry.
- Fix an unclear name with a better name, not with a comment.
- Comments explain **why** (a non-obvious constraint, a workaround, a chosen
  trade-off) — never **what** the code plainly already says.
- Do not add a docstring to a function just because it is a function. A short,
  well-named helper whose contract is obvious from its signature needs none.
- One good module- or public-API-level docstring beats a docstring on every
  private helper.

### 2. No abstraction until there are two real uses
- No interface / ABC / `Protocol` with a single implementation.
- No factory, builder, or registry for one constructor.
- No config or "params" object passed to exactly one call site — pass the
  arguments.
- No pass-through wrapper: if a function's body is just `return other(...)` with
  the same arguments, call `other` directly.
- Inheritance only for genuine substitutable subtypes; prefer a plain function.

### 3. Solve the instruction, not a generalized version of it
- No extensibility hooks, plugin points, options, flags, or parameters that
  nothing in the instruction or tests exercises (YAGNI).
- No "for future use" fields, branches, or return values.
- Handle the cases the problem has. Do not invent cases to handle.

### 4. Validate only at trust boundaries
- No defensive checks for states the caller cannot produce.
- Validate input where untrusted data enters (a public API, parsing external
  input); trust your own internal callers.
- Let unexpected conditions raise — do not wrap everything in try/except.

### 5. Reach for the standard library and built-ins first
- `sum(...)`, not `reduce(lambda ...)`; a comprehension, not a manual
  accumulator loop; `collections`/`itertools`/`dataclasses` over hand-rolled
  equivalents.
- Don't reimplement what the language or stdlib already gives you.

### 6. Every function and class must earn its existence
- Extract a helper when it removes real duplication or names a genuinely
  separate step — not to hit a line-count target.
- A class with a single method that isn't `__init__` should probably be a
  function.
- If a helper is called once and reads as an inline step, inline it.

## The mindset

You are done when you cannot remove anything else without losing behavior the
instruction or tests require — not when you have added everything that might
conceivably help.
