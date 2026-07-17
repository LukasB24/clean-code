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
| NM201 | short-name | `min_length=3, allowed=[i,j,k,n,x,y,_,id,ok,fh]` | warning |
| NM202 | meaningless-name | configurable ban lists | warning |
| NM203 | cryptic-abbreviation | `known_abbrevs=[cfg,ctx,idx,…]` | info |
| CM301 | docstring-restates-name | `overlap=0.7` | warning |
| CM302 | comment-restates-code | `overlap=0.7, min_words=2` | warning |
| CM303 | comment-density | `max_ratio=0.3, min_code_lines=5` | info |
| CM304 | boilerplate-param-docs | `min_uninformative=0.5` | warning |
| CM305 | file-comment-density | `max_ratio=0.2, min_code_lines=30` | warning |
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
| SD801 | type-switch-violates-ocp | `min_branches=3` | warning |
| SD802 | low-cohesion-class | `min_methods=4` | warning |
| DP701 | duplicate-function-body | `min_statements=4` | warning |
| DP702 | identical-function-implementation | `min_statements=2` | warning |
| PY901 | bare-except | — | warning |
| PY902 | empty-exception-handler | — | warning |

## A few details worth knowing

- **Naming rules look at binding sites only** — a bad name is reported once,
  where it's introduced. Loop/comprehension/lambda letters, `except ... as e`,
  `TypeVar`, and `ALL_CAPS` constants are exempt.
- **CM301/CM302 are deterministic, not LLM-judged** — they compare word
  overlap between a docstring/comment and the code it annotates. Comments
  explaining *why* (not *what*) are always exempt.
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
- **PY901 flags a bare `except:`** — it catches `KeyboardInterrupt` and
  `SystemExit` along with genuine bugs. `except Exception:` is merely broad,
  not bare, and is not flagged.
- **PY902 flags a handler whose body is entirely inert** (`pass`, `...`, or a
  lone string literal) — the exception is discarded with no log, fallback, or
  re-raise. A handler that `continue`s/`return`s/`break`s, logs, or re-raises
  is a real control-flow decision and is not flagged.
