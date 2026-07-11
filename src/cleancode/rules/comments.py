"""Comment and docstring noise rules (CM3xx).

These rules deterministically detect the classic LLM padding: docstrings that
restate the signature, comments that restate the code line, and Args sections
that document nothing. The core trick is word-overlap between the natural-
language text and the identifiers it sits next to.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable, Iterator

from cleancode.models import Comment, FileContext, Severity, Violation
from cleancode.rules.base import FRAMING_VERBS, Rule, content_words, split_identifier

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

# Comment prefixes that are directives or markers, never prose noise.
_EXEMPT_PREFIXES = (
    "todo", "fixme", "note", "xxx", "hack", "type:", "noqa", "cleancode:",
    "pragma", "pylint", "mypy:", "ruff:", "isort:", "fmt:", "!",
)

# Maps operators/keywords on a code line to the words a comment would use to
# describe them, so `x = x + 1  # increment x by one` scores as a restatement.
_OPERATOR_SYNONYMS: list[tuple[re.Pattern[str], frozenset[str]]] = [
    (re.compile(r"\+=|\+"), frozenset({"add", "adds", "plus", "increment", "increments", "increase", "sum", "append", "one", "1"})),
    (re.compile(r"-=|-"), frozenset({"subtract", "subtracts", "minus", "decrement", "decrements", "decrease", "one", "1"})),
    (re.compile(r"\*=|\*"), frozenset({"multiply", "multiplies", "times", "product"})),
    (re.compile(r"/=|/"), frozenset({"divide", "divides", "quotient", "half"})),
    (re.compile(r"=="), frozenset({"equals", "equal", "same", "matches", "check", "checks"})),
    (re.compile(r"!="), frozenset({"different", "unequal", "check", "checks"})),
    (re.compile(r"(?<![=<>!])=(?!=)"), frozenset({"set", "sets", "assign", "assigns", "store", "stores", "initialize", "initializes", "define", "defines", "make", "create", "creates"})),
    (re.compile(r"\bfor\b"), frozenset({"loop", "loops", "iterate", "iterates", "iterating", "go", "goes"})),
    (re.compile(r"\bwhile\b"), frozenset({"loop", "loops", "until", "repeat", "repeats"})),
    (re.compile(r"\bif\b"), frozenset({"check", "checks", "whether", "case", "condition"})),
    (re.compile(r"\breturn\b"), frozenset({"give", "gives", "back", "output", "outputs", "produce", "produces"})),
    (re.compile(r"\braise\b"), frozenset({"throw", "throws", "error", "errors", "exception"})),
    (re.compile(r"\bimport\b"), frozenset({"load", "loads", "bring", "module", "library", "libraries"})),
    (re.compile(r"\bopen\b"), frozenset({"read", "reads", "file"})),
    (re.compile(r"\.append\b"), frozenset({"add", "adds", "push", "pushes"})),
    (re.compile(r"\[.*\]"), frozenset({"index", "element", "item", "get", "gets", "slice"})),
    (re.compile(r"\bdef\b"), frozenset({"define", "defines", "declare", "declares"})),
    (re.compile(r"\bprint\b"), frozenset({"show", "shows", "display", "displays", "output", "outputs"})),
]

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"\b\d+\b")

# Generic filler that adds no information in a parameter description.
_GENERIC_PARAM_WORDS = frozenset(
    """
    parameter argument input output value object instance number string integer
    int float bool boolean list dict dictionary tuple set array data item items
    optional default variable name type
    """.split()
)

_SECTION_HEADER = re.compile(r"^\s*(args|arguments|parameters|returns|raises|yields)\s*:\s*$", re.IGNORECASE)
_PARAM_ENTRY = re.compile(r"^\s*(?P<name>\*{0,2}\w+)\s*(?:\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$")


def _functions(tree: ast.Module) -> Iterator[FunctionNode]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


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


def _code_line_words(code_text: str) -> set[str]:
    """All words a lazy comment could copy from this line of code."""
    words: set[str] = set()
    for identifier in _IDENTIFIER.findall(code_text):
        words.update(split_identifier(identifier))
    words.update(_NUMBER.findall(code_text))
    for pattern, synonyms in _OPERATOR_SYNONYMS:
        if pattern.search(code_text):
            words.update(synonyms)
    return words


class DocstringRestatesName(Rule):
    id = "CM301"
    name = "docstring-restates-name"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.8}
    description = (
        "Flags short docstrings whose words all come from the function signature "
        '(`def get_user_name`: """Gets the user name.""") — they cost reading time '
        "and add nothing."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        overlap_threshold = ctx.config.options["overlap"]
        for function in _functions(ctx.tree):
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
            else:
                continue
            yield self.violation(
                ctx,
                message,
                line=node.lineno,
                col=node.col_offset,
                suggestion=(
                    "delete it, or document what the name cannot say: why, edge cases, "
                    "units, invariants"
                ),
                symbol=function.name,
            )


class CommentRestatesCode(Rule):
    id = "CM302"
    name = "comment-restates-code"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.7, "min_words": 2}
    description = (
        "Flags comments that paraphrase the code line they annotate "
        "(`x = x + 1  # increment x by 1`). TODO/FIXME/NOTE and tool directives are exempt."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        overlap_threshold = ctx.config.options["overlap"]
        min_words = ctx.config.options["min_words"]
        for comment in ctx.comments:
            if _is_exempt(comment) or not comment.text:
                continue
            comment_words = content_words(comment.text)
            if len(comment_words) < min_words:
                continue
            code_text = self._annotated_code(ctx, comment)
            if code_text is None:
                continue
            code_words = _code_line_words(code_text)
            if len(comment_words & code_words) / len(comment_words) >= overlap_threshold:
                yield self.violation(
                    ctx,
                    f"comment restates the code it annotates: `# {comment.text}`",
                    line=comment.line,
                    col=comment.col,
                    suggestion="delete it; comments should explain *why*, not repeat *what*",
                )

    def _annotated_code(self, ctx: FileContext, comment: Comment) -> str | None:
        if comment.inline:
            return ctx.lines[comment.line - 1][: comment.col]
        comment_columns = {other.line: other.col for other in ctx.comments}
        for line_number in range(comment.line + 1, len(ctx.lines) + 1):
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
        for function in _functions(ctx.tree):
            code_lines, comment_lines = self._count_lines(ctx, function)
            if code_lines >= min_code_lines and comment_lines / code_lines > max_ratio:
                yield self.violation(
                    ctx,
                    f"function `{function.name}` has {comment_lines} comment lines "
                    f"for {code_lines} code lines (max ratio {max_ratio})",
                    line=function.lineno,
                    col=function.col_offset,
                    suggestion="strip comments that narrate the code; keep only the why",
                    symbol=function.name,
                )

    @staticmethod
    def _count_lines(ctx: FileContext, function: FunctionNode) -> tuple[int, int]:
        """Non-blank (code, comment) line counts inside one function body."""
        comment_only_lines = {comment.line for comment in ctx.comments if not comment.inline}
        inline_comment_lines = {comment.line for comment in ctx.comments if comment.inline}
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
        for function in _functions(ctx.tree):
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
                    f"docstring of `{function.name}` has boilerplate parameter docs: {pretty}",
                    line=node.lineno,
                    col=node.col_offset,
                    suggestion=(
                        "delete entries that restate the name; document only parameters "
                        "whose meaning, units, or constraints are not obvious"
                    ),
                    symbol=function.name,
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
