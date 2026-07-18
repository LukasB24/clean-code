"""Comment and docstring noise rules (CM3xx).

These rules deterministically detect the classic LLM padding: docstrings that
restate the signature, comments that restate the code line, and Args sections
that document nothing. The core trick is word-overlap between the natural-
language text and the identifiers it sits next to.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable, Iterator, NamedTuple

from cleancode.models import Comment, FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import (
    FRAMING_VERBS,
    FunctionNode,
    Rule,
    content_words,
    functions,
    split_identifier,
)

# Comment prefixes that are directives or markers, never prose noise.
_EXEMPT_PREFIXES = (
    "todo", "fixme", "note", "xxx", "hack", "type:", "noqa", "cleancode:",
    "pragma", "pylint", "mypy:", "ruff:", "isort:", "fmt:", "!",
)

# Maps operators/keywords on a code line to the words a comment would use to
# describe them, so `x = x + 1  # increment x by one` scores as a restatement.
# Each set holds one base word per concept; `_stem_candidates` normalizes
# comment words (adds -> add, iterating -> iterate, ...) before matching, so
# inflected forms don't need their own entries here.
_OPERATOR_SYNONYMS: list[tuple[re.Pattern[str], frozenset[str]]] = [
    (re.compile(r"\+=|\+"), frozenset({"add", "plus", "increment", "increase", "sum", "append", "one", "1"})),
    (re.compile(r"-=|-"), frozenset({"subtract", "minus", "decrement", "decrease", "one", "1"})),
    (re.compile(r"\*=|\*"), frozenset({"multiply", "times", "product"})),
    (re.compile(r"/=|/"), frozenset({"divide", "quotient", "half"})),
    (re.compile(r"=="), frozenset({"equal", "same", "match", "check"})),
    (re.compile(r"!="), frozenset({"different", "unequal", "check"})),
    (re.compile(r"(?<![=<>!])=(?!=)"), frozenset({"set", "assign", "store", "initialize", "define", "make", "create"})),
    (re.compile(r"\bfor\b"), frozenset({
        "loop", "iterate", "go", "repeat", "cycle", "time", "count",
    })),
    (re.compile(r"\bwhile\b"), frozenset({"loop", "until", "repeat"})),
    (re.compile(r"\bif\b"), frozenset({"check", "whether", "case", "condition"})),
    (re.compile(r"\breturn\b"), frozenset({"give", "back", "output", "produce"})),
    (re.compile(r"\braise\b"), frozenset({"throw", "error", "exception"})),
    (re.compile(r"\bimport\b"), frozenset({"load", "bring", "module", "library"})),
    (re.compile(r"\bopen\b"), frozenset({"read", "file"})),
    (re.compile(r"\.append\b"), frozenset({"add", "push"})),
    (re.compile(r"\[.*\]"), frozenset({"index", "element", "item", "get", "slice"})),
    (re.compile(r"\bdef\b"), frozenset({"define", "declare"})),
    (re.compile(r"\bprint\b"), frozenset({"show", "display", "output"})),
]

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"\b\d+\b")

# Spelled-out numbers, so `# iterate three times` matches a code-side `3`.
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "twenty": 20, "hundred": 100,
    "once": 1, "twice": 2, "thrice": 3,
}
_NUMBER_TO_WORDS: dict[str, frozenset[str]] = {
    str(target): frozenset(word for word, value in _NUMBER_WORDS.items() if value == target)
    for target in set(_NUMBER_WORDS.values())
}

# Generic filler that adds no information in a parameter description.
_GENERIC_PARAM_WORDS = frozenset(
    """
    parameter argument input output value object instance number string integer
    int float bool boolean list dict dictionary tuple set array data item items
    optional default variable name type
    """.split()
)

# Causal/justification markers: a comment carrying one of these explains
# *why*, so it's exempt from the restatement check regardless of overlap.
# One base form per concept; see `_stem_candidates` for the inflected-form
# matching (avoiding/avoids -> avoid, fixes/fixed -> fix, ...).
_WHY_SIGNALS = frozenset(
    """
    because since due workaround avoid prevent otherwise unless until
    require legacy compat compatible compatibility spec edge bug fix
    upstream vendor quirk compensate deliberately intentionally although
    though despite instead rather
    """.split()
)

_SECTION_HEADER = re.compile(r"^\s*(args|arguments|parameters|returns|raises|yields)\s*:\s*$", re.IGNORECASE)
_PARAM_ENTRY = re.compile(r"^\s*(?P<name>\*{0,2}\w+)\s*(?:\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$")


# (suffix, replacement endings to try once the suffix is stripped). "ing"/"ed"
# also try restoring a silent "e" (iterating -> iterat -> iterate).
_STEM_SUFFIX_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ies", ("y",)),
    ("es", ("",)),
    ("ing", ("", "e")),
    ("ed", ("", "e")),
    ("s", ("",)),
)
_MIN_STEM_LENGTH = 2


def _stem_candidates(word: str) -> frozenset[str]:
    """Heuristic English stem guesses for matching a word against a base-word dict.

    Not a real lemmatizer — over-generates candidates (multiple suffix-strip
    guesses, some of them non-words) so at least one hits the dict's base
    form; safe because the dicts this is matched against are small and
    hand-curated, not open vocabulary.
    """
    candidates = {word}
    for suffix, replacements in _STEM_SUFFIX_RULES:
        if suffix == "s" and word.endswith("ss"):
            continue
        if not word.endswith(suffix) or len(word) - len(suffix) < _MIN_STEM_LENGTH:
            continue
        stem = word[: -len(suffix)]
        candidates.update(stem + replacement for replacement in replacements)
    return frozenset(candidates)


def _stemmed(words: set[str]) -> set[str]:
    """Union of every word's stem candidates, so plural/tense variants match a base-word dict."""
    return {stem for word in words for stem in _stem_candidates(word)}


def _docstring_node(function: FunctionNode) -> ast.Constant | None:
    if not function.body:
        return None
    first = function.body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value
    return None


def _docstring_line_span(function: FunctionNode) -> set[int]:
    node = _docstring_node(function)
    if node is None:
        return set()
    return set(range(node.lineno, (node.end_lineno or node.lineno) + 1))


def _signature_words(function: FunctionNode) -> set[str]:
    words = set(split_identifier(function.name))
    for arg in [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]:
        words.update(split_identifier(arg.arg))
    return words


def _is_exempt(comment: Comment) -> bool:
    lowered = comment.text.lower()
    return any(lowered.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _informative(words: set[str]) -> set[str]:
    """Drop generic filler nouns so they can't pad the overlap-ratio denominator.

    `# increase a number` on `x += 1` should score on {increase} alone, not
    get diluted by "number" — a word no operator synonym table will ever
    match, yet carries no information either way.
    """
    filtered = words - _GENERIC_PARAM_WORDS
    return filtered or words


def _operator_synonym_words(code_text: str) -> set[str]:
    """Verb-like vocabulary a comment could use to describe this line's *operations*.

    Unlike `_code_line_words`, this skips identifiers entirely — matching a
    docstring against a whole function body (as CM301's body-paraphrase check
    does) can't treat "this docstring's noun happens to also be a variable
    name" as restatement, or every docstring that reuses its own domain
    vocabulary would get flagged.
    """
    words: set[str] = set()
    for numeral in _NUMBER.findall(code_text):
        words.add(numeral)
        words.update(_NUMBER_TO_WORDS.get(numeral, ()))
    for pattern, synonyms in _OPERATOR_SYNONYMS:
        if pattern.search(code_text):
            words.update(synonyms)
    return words


def _code_line_words(code_text: str) -> set[str]:
    """All words a lazy comment could copy from this line of code."""
    words: set[str] = set()
    for identifier in _IDENTIFIER.findall(code_text):
        words.update(split_identifier(identifier))
    words.update(_operator_synonym_words(code_text))
    return words


class _CommentLineIndex(NamedTuple):
    """Per-file split of `ctx.comments`, built once per `check()` call.

    `_function_body_words` used to rebuild this from `ctx.comments` on every
    call — once per function in the file — even though it doesn't depend on
    which function is being scanned. Building it once and threading it
    through turns that into O(comments) instead of O(functions x comments).
    """

    ctx: FileContext
    comment_only_lines: set[int]
    inline_comment_columns: dict[int, int]


def _build_comment_line_index(ctx: FileContext) -> _CommentLineIndex:
    comment_only_lines: set[int] = set()
    inline_comment_columns: dict[int, int] = {}
    for comment in ctx.comments:
        if comment.inline:
            inline_comment_columns[comment.lineno] = comment.col_offset
        else:
            comment_only_lines.add(comment.lineno)
    return _CommentLineIndex(ctx, comment_only_lines, inline_comment_columns)


def _nested_scope_lines(function: FunctionNode) -> set[int]:
    """Line numbers owned by a function/class nested inside `function`.

    `_function_body_words` scans raw line text with plain regexes, not the
    AST, so without this a nested function's own docstring or string
    literals would be scanned as if they were `function`'s code — English
    prose inside a nested docstring can coincidentally hit `\\bif\\b`,
    `\\bfor\\b`, etc. and leak unrelated operator-synonym words into
    `function`'s body vocabulary.
    """
    lines: set[int] = set()
    for node in ast.walk(function):
        if node is function or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    return lines


def _function_body_words(index: _CommentLineIndex, function: FunctionNode) -> set[str]:
    """Operator/keyword vocabulary (see `_operator_synonym_words`) for a function's own body.

    Unions the per-line synonym words across every body line so a docstring can
    be compared against what the *implementation does*, not just the signature.
    Docstring lines, comment-only lines, and any nested function/class's own
    lines are skipped; a line with a trailing inline comment only contributes
    its code portion.
    """
    excluded = _docstring_line_span(function) | _nested_scope_lines(function) | index.comment_only_lines
    start = function.body[0].lineno if function.body else function.lineno
    end = function.end_lineno or function.lineno
    words: set[str] = set()
    for line_number in range(start, end + 1):
        if line_number in excluded:
            continue
        text = index.ctx.lines[line_number - 1]
        column = index.inline_comment_columns.get(line_number)
        words.update(_operator_synonym_words(text[:column] if column is not None else text))
    return words


class DocstringRestatesName(Rule):
    id = "CM301"
    name = "docstring-restates-name"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.8, "body_overlap": 0.6}
    description = (
        "Flags short docstrings whose words all come from the function signature "
        '(`def get_user_name`: """Gets the user name.""") — they cost reading time '
        "and add nothing. Also flags docstrings that paraphrase what the body does "
        '(`def add(a, b)`: """Adds a and b and returns the sum.""") using the same '
        "operator-synonym vocabulary as CM302, so a paraphrase scores the same as a "
        "verbatim restatement. Docstrings carrying a causal/justification marker "
        "(because, since, workaround, instead, ...) are exempt from the body check "
        "— that's a *why*, not a *what*."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        overlap_threshold = ctx.config.options["overlap"]
        comment_index = _build_comment_line_index(ctx)
        for function in functions(ctx.tree):
            docstring = ast.get_docstring(function, clean=True)
            node = _docstring_node(function)
            if docstring is None or node is None:
                continue
            if len(docstring.strip().splitlines()) > 2:
                continue  # substantive multi-line docstrings are never flagged
            doc_words = content_words(docstring.splitlines()[0], extra_stopwords=FRAMING_VERBS)
            signature_words = _signature_words(function)
            if not doc_words:
                message = f"docstring of `{function.name}` carries no information"
            elif len(doc_words & signature_words) / len(doc_words) >= overlap_threshold:
                message = (
                    f"docstring of `{function.name}` only restates the function signature"
                )
            elif self._paraphrases_body(comment_index, function, doc_words):
                message = f"docstring of `{function.name}` only paraphrases the function body"
            else:
                continue
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message=message,
                    suggestion=(
                        "delete it, or document what the name cannot say: why, edge cases, "
                        "units, invariants"
                    ),
                    symbol=function.name,
                ),
            )

    def _paraphrases_body(self, index: _CommentLineIndex, function: FunctionNode, doc_words: set[str]) -> bool:
        """True when the docstring's words mostly duplicate the body's operations in synonym form."""
        if _stemmed(doc_words) & _WHY_SIGNALS:
            return False  # carries a rationale marker — that's a *why*, never a restatement
        informative = _informative(doc_words)
        body_words = _function_body_words(index, function)
        if not informative or not body_words:
            return False
        threshold = index.ctx.config.options["body_overlap"]
        return len(_stemmed(informative) & body_words) / len(informative) >= threshold


class CommentRestatesCode(Rule):
    id = "CM302"
    name = "comment-restates-code"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.7, "min_words": 2}
    description = (
        "Flags comments that paraphrase the code line they annotate "
        "(`x = x + 1  # increment x by 1`, `for k in range(3):  # iterate three "
        "times`). TODO/FIXME/NOTE, tool directives, and comments carrying a "
        "causal/justification marker (because, since, workaround, ...) are exempt."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for comment, comment_words in self._candidates(ctx):
            if self._restates_code(ctx, comment, comment_words):
                yield self.violation(
                    ctx,
                    comment,
                    ViolationDetails(
                        message=f"comment restates the code it annotates: `# {comment.text}`",
                        suggestion="delete it; comments should explain *why*, not repeat *what*",
                    ),
                )

    def _candidates(self, ctx: FileContext) -> Iterator[tuple[Comment, set[str]]]:
        """Yield (comment, words) for comments substantial enough to be worth checking."""
        min_words = ctx.config.options["min_words"]
        for comment in ctx.comments:
            if _is_exempt(comment) or not comment.text:
                continue
            comment_words = content_words(comment.text)
            if _stemmed(comment_words) & _WHY_SIGNALS:
                continue  # explains *why*, not *what* — never a restatement
            if len(comment_words) >= min_words:
                yield comment, _informative(comment_words)

    def _restates_code(
        self, ctx: FileContext, comment: Comment, comment_words: set[str]
    ) -> bool:
        """True when the comment's words mostly duplicate the code it annotates."""
        code_text = self._annotated_code(ctx, comment)
        if code_text is None:
            return False
        overlap_threshold = ctx.config.options["overlap"]
        code_words = _code_line_words(code_text)
        return len(_stemmed(comment_words) & code_words) / len(comment_words) >= overlap_threshold

    def _annotated_code(self, ctx: FileContext, comment: Comment) -> str | None:
        if comment.inline:
            return ctx.lines[comment.lineno - 1][: comment.col_offset]
        comment_columns = {other.lineno: other.col_offset for other in ctx.comments}
        for line_number in range(comment.lineno + 1, len(ctx.lines) + 1):
            text = ctx.lines[line_number - 1]
            stripped = text.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            column = comment_columns.get(line_number)
            return text[:column] if column is not None else text
        return None


class CommentDensity(Rule):
    id = "CM303"
    name = "comment-density"
    default_severity = Severity.INFO
    default_options = {"max_ratio": 0.3, "min_code_lines": 5}
    description = (
        "Flags functions with more than ~1 comment line per 3 code lines — a strong "
        "smell of generated padding. Docstrings are policed by CM301/CM304, not here."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_ratio = ctx.config.options["max_ratio"]
        min_code_lines = ctx.config.options["min_code_lines"]
        for function in functions(ctx.tree):
            code_lines, comment_lines = self._count_lines(ctx, function)
            if code_lines >= min_code_lines and comment_lines / code_lines > max_ratio:
                yield self.violation(
                    ctx,
                    function,
                    ViolationDetails(
                        message=f"function `{function.name}` has {comment_lines} comment lines "
                        f"for {code_lines} code lines (max ratio {max_ratio})",
                        suggestion="strip comments that narrate the code; keep only the why",
                        symbol=function.name,
                    ),
                )

    @staticmethod
    def _count_lines(ctx: FileContext, function: FunctionNode) -> tuple[int, int]:
        """Non-blank (code, comment) line counts inside one function body."""
        comment_only_lines: set[int] = set()
        inline_comment_lines: set[int] = set()
        for comment in ctx.comments:
            target = inline_comment_lines if comment.inline else comment_only_lines
            target.add(comment.lineno)
        docstring_lines = _docstring_line_span(function)

        code_lines = 0
        comment_lines = 0
        for line_number in range(function.lineno, (function.end_lineno or function.lineno) + 1):
            stripped = ctx.lines[line_number - 1].strip()
            if not stripped or line_number in docstring_lines:
                continue
            if line_number in comment_only_lines:
                comment_lines += 1
                continue
            code_lines += 1
            if line_number in inline_comment_lines:
                comment_lines += 1
        return code_lines, comment_lines


class BoilerplateParamDocs(Rule):
    id = "CM304"
    name = "boilerplate-param-docs"
    default_severity = Severity.WARNING
    default_options = {"min_uninformative": 0.5}
    description = (
        "Flags Google-style Args:/Returns: sections where entries like "
        "`data: The data.` describe nothing beyond the parameter name."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        min_uninformative = ctx.config.options["min_uninformative"]
        for function in functions(ctx.tree):
            docstring = ast.get_docstring(function, clean=True)
            node = _docstring_node(function)
            if docstring is None or node is None:
                continue
            entries = list(self._section_entries(docstring, function))
            if not entries:
                continue
            uninformative = [name for name, is_noise in entries if is_noise]
            if len(uninformative) / len(entries) >= min_uninformative:
                pretty = ", ".join(f"`{name}`" for name in uninformative)
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"docstring of `{function.name}` has boilerplate parameter "
                        f"docs: {pretty}",
                        suggestion=(
                            "delete entries that restate the name; document only parameters "
                            "whose meaning, units, or constraints are not obvious"
                        ),
                        symbol=function.name,
                    ),
                )

    def _section_entries(
        self, docstring: str, function: FunctionNode
    ) -> Iterator[tuple[str, bool]]:
        """Yield (entry_name, is_uninformative) for Args:/Returns: style entries."""
        in_section = False
        section_name = ""
        for line in docstring.splitlines():
            header = _SECTION_HEADER.match(line)
            if header:
                in_section = True
                section_name = header.group(1).lower()
                continue
            if not in_section:
                continue
            if line.strip() and not line.startswith((" ", "\t")):
                in_section = False  # dedented text ends the section
                continue
            entry = _PARAM_ENTRY.match(line)
            if entry is None:
                continue
            name = entry.group("name").lstrip("*")
            description = entry.group("desc").strip()
            if section_name in ("returns", "raises", "yields"):
                reference = set(split_identifier(function.name))
            else:
                reference = set(split_identifier(name))
            desc_words = content_words(description, extra_stopwords=FRAMING_VERBS)
            uninformative = desc_words <= (reference | _GENERIC_PARAM_WORDS)
            yield name, uninformative
