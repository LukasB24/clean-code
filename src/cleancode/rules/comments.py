"""Comment noise rules (CM302, CM303, CM305).

These rules deterministically detect the classic LLM padding: comments that
restate the code line they annotate, and comment-heavy functions or files.
Docstring noise is policed by the CM301/CM304 rules in ``docstrings.py``.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable, Iterator

from cleancode.models import (
    Comment,
    FileContext,
    ModuleTop,
    Severity,
    Violation,
    ViolationDetails,
)
from cleancode.rules.base import (
    GENERIC_PARAM_WORDS,
    IDENTIFIER,
    FunctionNode,
    Rule,
    content_words,
    docstring_node,
    end_line,
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


_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _docstring_line_span(owner: ast.Module | ast.ClassDef | FunctionNode) -> set[int]:
    node = docstring_node(owner)
    if node is None:
        return set()
    return set(range(node.lineno, end_line(node) + 1))


def _all_docstring_lines(tree: ast.Module) -> set[int]:
    """Line numbers covered by any module, class, or function docstring."""
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, _DOCSTRING_OWNERS):
            lines.update(_docstring_line_span(node))
    return lines


def _is_exempt(comment: Comment) -> bool:
    lowered = comment.text.lower()
    return any(lowered.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _informative(words: set[str]) -> set[str]:
    """Drop generic filler nouns so they can't pad the overlap-ratio denominator.

    `# increase a number` on `x += 1` should score on {increase} alone, not
    get diluted by "number" — a word no operator synonym table will ever
    match, yet carries no information either way.
    """
    filtered = words - GENERIC_PARAM_WORDS
    return filtered or words


def _code_line_words(code_text: str) -> set[str]:
    """All words a lazy comment could copy from this line of code."""
    words: set[str] = set()
    for identifier in IDENTIFIER.findall(code_text):
        words.update(split_identifier(identifier))
    for numeral in _NUMBER.findall(code_text):
        words.add(numeral)
        words.update(_NUMBER_TO_WORDS.get(numeral, ()))
    for pattern, synonyms in _OPERATOR_SYNONYMS:
        if pattern.search(code_text):
            words.update(synonyms)
    return words


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
        for function in ctx.functions:
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
        for line_number in range(function.lineno, end_line(function) + 1):
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


def _comment_line_sets(comments: list[Comment]) -> tuple[set[int], set[int], set[int]]:
    """Line sets for density counting: (standalone, counted standalone, counted inline).

    A standalone comment line is never code; only non-exempt comments count
    toward density.
    """
    standalone: set[int] = set()
    counted_standalone: set[int] = set()
    counted_inline: set[int] = set()
    for comment in comments:
        counted = counted_inline if comment.inline else counted_standalone
        if not _is_exempt(comment):
            counted.add(comment.lineno)
        if not comment.inline:
            standalone.add(comment.lineno)
    return standalone, counted_standalone, counted_inline


class FileCommentDensity(Rule):
    id = "CM305"
    name = "file-comment-density"
    default_severity = Severity.WARNING
    default_options = {"max_ratio": 0.2, "min_code_lines": 30}
    description = (
        "Flags a file whose overall comment density exceeds `max_ratio` (default 1 "
        "comment line per 5 code lines) — file-wide comment sprawl that CM303 misses "
        "when no single function is dense enough on its own. Directive comments "
        "(TODO, noqa, `cleancode:`, ...) and docstrings (policed by CM301/CM304) "
        "don't count, and files with fewer than `min_code_lines` code lines are "
        "never flagged."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_ratio = ctx.config.options["max_ratio"]
        min_code_lines = ctx.config.options["min_code_lines"]
        code_lines, comment_lines = self._count_file_lines(ctx)
        if code_lines >= min_code_lines and comment_lines / code_lines > max_ratio:
            yield self.violation(
                ctx,
                ModuleTop(),
                ViolationDetails(
                    message=f"file has {comment_lines} comment lines for {code_lines} "
                    f"code lines (max ratio {max_ratio})",
                    suggestion=(
                        "analyze every comment in this file and keep only those that say "
                        "something the code cannot — delete narration, restatements, and "
                        "section banners"
                    ),
                ),
            )

    @staticmethod
    def _count_file_lines(ctx: FileContext) -> tuple[int, int]:
        """Non-blank (code, comment) line counts across the whole file."""
        standalone_lines, counted_standalone, counted_inline = _comment_line_sets(ctx.comments)
        docstring_lines = _all_docstring_lines(ctx.tree)
        code_lines = 0
        comment_lines = 0
        for line_number, line in enumerate(ctx.lines, start=1):
            if not line.strip() or line_number in docstring_lines:
                continue
            if line_number in counted_standalone:
                comment_lines += 1
                continue
            if line_number in standalone_lines:
                continue  # exempt directive on its own line: neither code nor comment
            code_lines += 1
            if line_number in counted_inline:
                comment_lines += 1
        return code_lines, comment_lines
