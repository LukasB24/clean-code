# Rule reference

The full list of rules clean-code checks, with their IDs, default options, and
default severities. This is the detailed reference — for the pitch and a
quick-start, see the [README](../README.md).

`cleancode rules` prints this same list from the CLI, with full descriptions.

| ID | Name | Default | Severity |
|----|------|---------|----------|
| ST101 | max-nesting-depth | `max_depth=2` | error |
| ST102 | max-function-length | `max_lines=60` | warning |
| ST103 | max-class-length | `max_lines=200` | warning |
| ST104 | max-parameters | `max_params=3` | warning |
| ST105 | max-complexity | `max_complexity=10` | error |
| ST106 | do-one-thing | `conjunctions=[and, or]` | warning |
| ST107 | too-many-guard-clauses | `max_guards=2` | info |
| ST108 | max-module-length | `max_lines=500` | warning |
| ST109 | redundant-else | — | warning |
| NM201 | short-name | `min_length=3, allowed=[i,j,k,n,x,y,_,id,ok,fh]` | warning |
| NM202 | meaningless-name | configurable ban lists | warning |
| NM203 | cryptic-abbreviation | `known_abbrevs=[cfg,ctx,idx,…]` | info |
| CM301 | docstring-restates-name | `overlap=0.6, private_overlap=0.35, body_overlap=0.6` | warning |
| CM302 | comment-restates-code | `overlap=0.5, min_words=2` | warning |
| CM303 | comment-density | `max_ratio=0.3, min_code_lines=5` | info |
| CM304 | boilerplate-param-docs | `min_uninformative=0.5` | warning |
| CM305 | file-comment-density | `max_ratio=0.2, min_code_lines=30` | warning |
| CM306 | banner-comment | — | warning |
| CM307 | docstring-semantic-restatement | `threshold=0.75, min_words=3, max_lines=3` | warning |
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
| SM612 | unused-binding | — | warning |
| SM613 | builtin-shadowing | `watched=[id,type,list,dict,str,…]` | warning |
| SM614 | bool-arithmetic | — | warning |
| SM615 | nested-ternary | — | warning |
| SM616 | callable-indirection | — | warning |
| SM617 | deep-expression | `max_depth=4` | warning |
| SM618 | thin-delegation-wrapper | — | warning |
| SM619 | buried-value-fallback | — | warning |
| SM620 | returned-temp | — | warning |
| SM621 | compatibility-alias | — | warning |
| SM622 | trivial-property-pair | — | warning |
| SD801 | type-switch-violates-ocp | `min_branches=3` | warning |
| SD802 | low-cohesion-class | `min_methods=4` | warning |
| SD803 | class-as-namespace | `min_methods=2` | warning |
| DP701 | duplicate-function-body | `min_statements=4` | warning |
| DP702 | identical-function-implementation | `min_statements=2` | warning |
| PY901 | bare-except | — | warning |
| PY902 | empty-exception-handler | — | warning |
| PY903 | oversized-try | `max_statements=3` | warning |

## A few details worth knowing

- **Naming rules look at binding sites only** — a bad name is reported once,
  where it's introduced. Loop/comprehension/lambda letters, `except ... as e`,
  `TypeVar`, and `ALL_CAPS` constants are exempt.
- **CM301/CM302 are deterministic, not LLM-judged** — they compare word
  overlap between a docstring/comment and the code it annotates. Comments
  explaining *why* (not *what*) are always exempt.
- **CM301 judges a `_`-prefixed (private) function/class at a much stricter
  `private_overlap` (default 0.35) than a public one (`overlap`, default
  0.6)** — a private name has no external reader to write prose for, only
  its own body, which the reader can just read instead. Dunders are judged
  as public, not private.
- **CM301 also catches a *paraphrased* body**, not just a verbatim one: a
  function docstring whose words are mostly synonyms of its body's
  operators/keywords (`"""Adds two numbers and returns the sum."""` over
  `return a + b`) is flagged at `body_overlap`, reusing CM302's
  operator-synonym table (`+` → add/plus/sum/…, `for` → loop/iterate/…)
  against the *whole* function body rather than one annotated line. A
  why-signal docstring (because, workaround, instead, ...) is exempt from
  this check, same as CM302's comments.
- **CM307 is the semantic second tier behind CM301/CM302** — a vendored
  pretrained-embedding classifier (pure numpy, no ML framework, deterministic,
  microseconds per comment) scores each *clause* of a docstring/comment as
  procedural narration vs. rationale, catching the more diffuse synonym
  paraphrases that even CM301's operator-anchored body check can't reach
  (loose narration with no strong operator/keyword anchor). A text is
  flagged only when every clause is verb-led narration scoring above
  `threshold`; one rationale clause, noun-led value contract, or
  unknown-vocabulary clause clears it. Anything CM301/CM302 already flag —
  including CM301's operator-synonym body check — is skipped, so the two
  rules never double-report the same paraphrase; scope is limited to
  undecorated function docstrings of at most `max_lines` lines plus
  standalone comment blocks. The backbone (`embeddings.npz`) is a Llama
  2-derived asset under its own license, not this project's Apache-2.0 —
  see `src/cleancode/semantics/THIRD_PARTY_NOTICES/`. Its classifier head
  is fit on an 80/10/10 train/val/test split of `tools/data/what_why.jsonl`
  (`tools/train_head.py`); `head.json`'s `training.accuracy` reports all
  three so the checked-in figure reflects held-out generalization, not
  just training-set fit.
- **CM301 also covers class docstrings** (reference words = the class name
  plus its directly-defined method names) and, for docstrings longer than
  two lines, flags one whose *every* non-empty line never leaves the
  signature/class-name vocabulary plus generic parameter nouns — one
  informative line anywhere is enough to clear it.
- **A short (two-line-or-fewer) function docstring is also judged against
  the function's own source text**, not just its name and parameters — a
  plain scan for identifier- and keyword-shaped words (the same technique
  `CM302` uses on one code line, extended to the whole body), including
  words that are only string-constant values the body switches on. A
  docstring that just paraphrases what the code already shows — return
  values, local variable names, the branches it takes — restates the code,
  not just the signature, and is flagged the same way. This widened
  reference applies only to the short-docstring check; a longer, multi-line
  docstring is still judged purely against the signature/class vocabulary,
  so substantive prose that happens to reuse the function's own words for
  good reason isn't penalized.
- **CM305 measures comment density file-wide** where CM303 measures it per
  function, so it catches comment sprawl spread across module level and many
  small functions. It counts non-blank comment lines against code lines
  (an inline comment counts as +1 comment on its code line); directive
  comments (TODO/FIXME, `noqa`, `cleancode:`, shebangs, ...) and docstrings
  (CM301/CM304's territory) count toward neither side. Its suggestion is
  written for an LLM fixer: analyze every comment in the file and keep only
  those that say something the code cannot.
- **SL401/SL402 score subscript complexity** (dimensions, steps, nesting,
  chaining) and ignore type annotations like `dict[str, int]`.
- **SM6xx catches structural smells node-counting misses**: nested
  comprehensions, anonymous tuple indexing, magic-string branching, redundant
  ternaries, `reduce` instead of `sum`, repeated iteration, magic numbers,
  non-idiomatic emptiness checks, PyTorch `Dataset` pitfalls (eager
  loading, premature `.cuda()`, redundant `isinstance` on an annotated type),
  and unused imports/local variables.
- **SM612 skips `__init__.py`** for the unused-import half (imports there are
  usually deliberate re-exports), exempts `__all__`-exported names,
  `global`/`nonlocal` names, and forward-reference string annotations
  (`ctx: "FileContext"`), only flags a multi-target unpack (`a, b = pair()`)
  when *every* target in it is unused, counts an explicit `del` as a use,
  and bails out of the unused-variable check entirely for a function that
  calls `locals`/`eval`/`exec`.
- **SM614–SM617 stop complexity from being *compressed* instead of removed.**
  The structural limits (ST1xx) can be satisfied by squeezing the same logic
  into denser expressions — that's what these four catch: a boolean added to
  a counter (`count += x in seen`, SM614), a ternary inside a ternary
  (SM615), a function that returns a `lambda`/`functools.partial`/bare
  function reference instead of doing work (SM616), and a statement nesting
  calls/comprehensions/f-strings more than `max_depth` levels deep (SM617 —
  a *flat* `and`-chain of conditions stays fine at any length, and
  module-level constant tables are exempt).
- **SM618 flags a private thin-delegation wrapper**: a function whose whole
  body is `return <one call to another function>`. Public functions
  (API conveniences), decorated functions, dunders, calls to a builtin
  (`return any(...)`), and calls on the function's own parameters
  (`return name.startswith("_")`) are exempt — only a genuine private hop
  to unrelated work is flagged.
- **SM619 flags a boolean fallback (`a or b`) used as a value inside a
  larger expression** — an arithmetic operand or subscript index, where the
  operator is easy to misread (`(node.end_lineno or node.lineno) + 1`). A
  bare `x = a or b` and ordinary boolean conditions (`if`/`while` tests,
  `not (a and b)`) are exempt.
- **SM613 reuses the same binding-site collection as the `NM2xx` naming
  rules** (parameters, assignment/`for`/`with ... as`/comprehension targets,
  function/class names), so class/instance attributes (`self.id`), dict keys,
  and call-site keyword arguments are never flagged — only genuine scope
  shadowing. The default `watched` list narrows the check to builtins most
  often reused as domain terms (`id`, `type`, `list`, ...); every entry is
  still verified against the live `builtins` module, not a hardcoded copy.
- **`elif` chains don't count as nesting** for ST101 (they still count toward
  ST105 complexity).
- **ST109 flags a plain two-way `if`/`else` whose `if` branch always exits**
  (return/raise/break/continue) — the else adds an indentation level the exit
  already made unnecessary. Any `if` that is itself part of an `elif` chain
  is exempt entirely: a multi-way dispatch ladder ending in `else` is
  idiomatic, not the redundant-nesting shape this targets, even when every
  branch in the chain returns.
- **CM306 flags a decoration-only or decoration-framed comment**
  (`# ----------`, `# ---- Step 1 ----`) — section-divider ceremony that
  carries no information the code doesn't already show. It reuses the same
  directive-comment exemptions as CM303/CM305 (TODO/FIXME/NOTE, `noqa`,
  `cleancode:`, ...); a plain narrative comment with no decoration characters
  (`# Step 1: parse the input`) is left to CM302/CM305, not flagged here.
- **SD801 flags a same-variable type-switch** (`isinstance`/`type()` chain) —
  an Open/Closed Principle smell. Dispatching on Python's own `ast.*` node
  types is exempt, since that's routine AST tooling, not the smell targeted.
- **SD802 flags a class whose methods split into 2+ genuine multi-member
  clusters** sharing no state or calls — an SRP smell beyond ST103's line
  count. A lone method with no shared state doesn't count as its own cluster,
  property getter/setter pairs are treated as one method, and classes named
  with a configurable `exempt_name_suffixes` (default `Mixin`) are exempt
  entirely — mixins are intentionally composed from independent behavior.
- **DP701 flags copy-pasted function bodies** (once names are ignored) across
  the whole run — it only catches cross-file duplicates when you check a
  directory containing both files, not one file at a time. Called function/
  method names are *not* ignored: two same-shaped bodies that invoke
  different APIs are doing different things, not copy-pasting each other.
  That includes the receiver when it is an imported module (`json.dumps`
  vs `yaml.dumps`); a variable receiver (`fh.write` vs `out.write`) is
  ignored like any other local name, since that's just a rename.
- **DP702 flags exactly identical bodies, identifiers included** — the same
  helper pasted into two places. Requiring identifiers to match lets it
  inspect much shorter bodies (default 2 statements) than DP701 without
  noise; a group long enough for DP701 to report is left to DP701 so one
  copy-paste never produces two violations.
- **ST108 counts a module's total lines** (blank lines and comments
  included, mirroring how a reader scrolls a file) against `max_lines`.
- **SM620 flags `name = expr` immediately followed by `return name`**, where
  `name` has no other use in the function — the assignment adds a name but
  no information. An annotated assignment (`name: T = expr`) is exempt,
  since the annotation itself is informative; a name used again before the
  return (logged, passed to another call) is exempt too.
- **SM621 flags a module-level `alias = original`** where `original` is a
  function or class defined in the same file — a second name for something
  that already has one, the kind of "kept for backwards compatibility" alias
  that only makes sense in a mature library, not freshly generated code.
  ALL_CAPS targets, `_`-prefixed targets, and annotated assignments
  (`TypeAlias`) are exempt.
- **SM622 flags a `@property`/`@x.setter` pair that only mirrors
  `self._x`** — both accessors trivial, with no validation or computation in
  either. A getter-only read-only property (no matching setter) is a
  legitimate idiom and is exempt entirely; SD802 already treats a property
  pair as one method for cohesion purposes, the same precedent this rule's
  pair-detection follows.
- **SD803 flags a class with no base classes, no decorators, and no
  class-level state** whose entire body (docstring aside) is
  `min_methods`-or-more `@staticmethod`s — the class carries no state, so
  the module is already the namespace it's imitating. Any base class,
  decorator, or class-level assignment exempts the class entirely; a single
  static helper alongside instance methods is untouched (only an *all*-static
  body counts).
- **PY901 flags a bare `except:`** — it catches `KeyboardInterrupt` and
  `SystemExit` along with genuine bugs. `except Exception:` is merely broad,
  not bare, and is not flagged.
- **PY902 flags a handler whose body is entirely inert** (`pass`, `...`, or a
  lone string literal) — the exception is discarded with no log, fallback, or
  re-raise. A handler that `continue`s/`return`s/`break`s, logs, or re-raises
  is a real control-flow decision and is not flagged.
- **PY903 flags a `try` spanning more than `max_statements` top-level
  statements feeding a bare or `except Exception`/`BaseException` handler** —
  the handler can't know which of several steps actually failed. The
  conjunction is deliberate: a long `try` narrowed to a specific exception is
  a deliberate contract and isn't flagged, and a short `try` (at or under
  `max_statements`) wrapping a broad handler is a common, harmless top-level
  guard and isn't flagged either.
