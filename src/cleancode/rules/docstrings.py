"""Docstring noise rules (CM301, CM304). CM307 lives in ``semantic_restatement.py``.

These rules deterministically detect the classic LLM docstring padding: a
docstring that restates the signature or paraphrases the body (verbatim, or
in synonym form via the same operator-synonym table CM302 uses), and Args
sections that document nothing.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import (
    FRAMING_VERBS,
    GENERIC_PARAM_WORDS,
    IDENTIFIER,
    WHY_SIGNALS,
    FunctionNode,
    Rule,
    content_words,
    docstring_node,
    end_line,
    is_private,
    split_identifier,
    stemmed,
)
from cleancode.rules.comments import operator_synonym_words

_SECTION_HEADER = re.compile(r"^\s*(args|arguments|parameters|returns|raises|yields)\s*:\s*$", re.IGNORECASE)
_PARAM_ENTRY = re.compile(r"^\s*(?P<name>\*{0,2}\w+)\s*(?:\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$")


def _signature_words(function: FunctionNode) -> set[str]:
    words = set(split_identifier(function.name))
    for arg in [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]:
        words.update(split_identifier(arg.arg))
    return words


def _body_source_words(function: FunctionNode, lines: list[str]) -> set[str]:
    """Words appearing anywhere in ``function``'s own source, docstring excluded.

    A short docstring whose every word already appears in the code it
    documents adds nothing — the same principle ``CM302`` applies to a
    single line of code, extended to a whole function body. This is a plain
    text scan (like ``CM302``'s ``_code_line_words``), so it also catches a
    docstring paraphrase of a string constant the body switches on
    (``section_name in ("returns", "raises", "yields")``), not just of a
    real identifier.
    """
    doc_node = docstring_node(function)
    if doc_node is None:
        doc_span: set[int] = set()
    else:
        doc_span = set(range(doc_node.lineno, end_line(doc_node) + 1))
    words: set[str] = set()
    for line_number in range(function.lineno, end_line(function) + 1):
        if line_number in doc_span:
            continue
        for identifier in IDENTIFIER.findall(lines[line_number - 1]):
            words.update(split_identifier(identifier))
    return words


def _nested_def_lines(function: FunctionNode) -> set[int]:
    """Line numbers owned by a function/class defined inside ``function``.

    ``_function_operator_words`` scans raw line text with plain regexes, not
    the AST, so without this a nested function's own docstring would be
    scanned as if it were ``function``'s code — prose inside it can
    coincidentally hit a keyword pattern (``\\bif\\b`` etc.) and leak
    unrelated vocabulary into the outer function's body words.
    """
    lines: set[int] = set()
    for node in ast.walk(function):
        if node is function or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        lines.update(range(node.lineno, end_line(node) + 1))
    return lines


def _comment_line_index(comments: list) -> tuple[set[int], dict[int, int]]:
    """Bucketed once so callers scanning many source lines never re-walk ``comments`` per candidate."""
    comment_only_lines: set[int] = set()
    inline_columns: dict[int, int] = {}
    for comment in comments:
        if comment.inline:
            inline_columns[comment.lineno] = comment.col_offset
        else:
            comment_only_lines.add(comment.lineno)
    return comment_only_lines, inline_columns


def _function_operator_words(function: FunctionNode, ctx: FileContext) -> set[str]:
    """Operator/keyword synonym vocabulary of ``function``'s own body.

    A docstring whose words are mostly synonyms of the body's operators
    ("Adds two numbers and returns the sum." over ``return a + b``) is a
    restatement even with zero literal identifier overlap — the same
    paraphrase pattern CM302 already catches for a single annotated code
    line, extended here to a whole function body.
    """
    doc_node = docstring_node(function)
    doc_span: set[int] = set()
    if doc_node is not None:
        doc_span = set(range(doc_node.lineno, end_line(doc_node) + 1))
    comment_only_lines, inline_columns = _comment_line_index(ctx.comments)
    excluded = doc_span | _nested_def_lines(function) | comment_only_lines

    start = function.body[0].lineno if function.body else function.lineno
    words: set[str] = set()
    for line_number in range(start, end_line(function) + 1):
        if line_number in excluded:
            continue
        line_text = ctx.lines[line_number - 1]
        column = inline_columns.get(line_number)
        words.update(operator_synonym_words(line_text[:column] if column is not None else line_text))
    return words


def _operator_paraphrase_reason(text: str, operator_words: set[str], threshold: float) -> str | None:
    """Why ``text`` paraphrases the function body's operations in synonym form, else ``None``.

    A docstring carrying a why-signal word is exempt regardless of
    overlap — same short-circuit CM302 uses for comments — since explaining
    *why* is never a restatement of *what*.
    """
    if not operator_words:
        return None
    words = content_words(text, extra_stopwords=FRAMING_VERBS)
    if not words or stemmed(words) & WHY_SIGNALS:
        return None
    informative = words - GENERIC_PARAM_WORDS or words
    overlap = len(stemmed(informative) & operator_words) / len(informative)
    return "paraphrases the function body's operations" if overlap >= threshold else None


def _class_reference_words(class_def: ast.ClassDef) -> set[str]:
    """Class name plus its directly-defined method names — what a class docstring may restate."""
    words = set(split_identifier(class_def.name))
    for item in class_def.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            words.update(split_identifier(item.name))
    return words


def _short_docstring_reason(text: str, reference: set[str], overlap_threshold: float) -> str | None:
    """Why a docstring of two lines or fewer says nothing beyond ``reference``, else ``None``."""
    words = content_words(text, extra_stopwords=FRAMING_VERBS)
    if not words:
        return "carries no information"
    if len(words & reference) / len(words) >= overlap_threshold:
        return "only restates the signature"
    return None


def _long_docstring_reason(text: str, reference: set[str]) -> str | None:
    """Why a longer docstring's every line stays within signature + generic filler, else ``None``.

    One informative line is enough to clear a multi-line docstring, so this
    only fires when the whole thing — every non-empty line — never leaves
    the vocabulary a signature and generic parameter nouns already cover.
    """
    lines = [line for line in text.strip().splitlines() if line.strip()]
    allowed = reference | GENERIC_PARAM_WORDS
    per_line_words = [content_words(line, extra_stopwords=FRAMING_VERBS) for line in lines]
    if per_line_words and all(words <= allowed for words in per_line_words):
        return "never says anything beyond the name"
    return None


@dataclass(frozen=True)
class _DocstringOwner:
    """The bits of a function/class ``CM301`` needs, independent of which it is.

    ``short_reference`` is only ever used to judge a two-line-or-fewer
    docstring; it additionally includes the owner's own source text for a
    function (see ``_body_source_words``), so a short docstring that
    paraphrases the code right below it — not just the signature — still
    counts as a restatement. ``reference`` (signature/class words alone)
    is what a longer, multi-line docstring is judged against: folding body
    words into that check too would make genuinely informative prose look
    like a restatement merely for reusing the function's own vocabulary.
    ``operator_words`` is empty for a class — there's no single body to
    compare operator/keyword vocabulary against.
    """

    node: FunctionNode | ast.ClassDef
    name: str
    reference: set[str]
    short_reference: set[str]
    operator_words: set[str] = frozenset()


@dataclass(frozen=True)
class _OverlapThresholds:
    """The two thresholds ``_restatement`` judges a docstring against, bundled to keep call sites at one argument."""

    signature: float
    body_overlap: float


def _owners(ctx: FileContext) -> Iterator[_DocstringOwner]:
    for function in ctx.functions:
        signature = _signature_words(function)
        body_words = _body_source_words(function, ctx.lines)
        operator_words = _function_operator_words(function, ctx)
        yield _DocstringOwner(function, function.name, signature, signature | body_words, operator_words)
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.ClassDef):
            reference = _class_reference_words(node)
            yield _DocstringOwner(node, node.name, reference, reference)


def _restatement(
    owner: "_DocstringOwner", thresholds: _OverlapThresholds
) -> tuple[ast.Constant, str] | None:
    """The docstring node and why it's a restatement, or ``None``.

    Three checks, in order: signature/body-identifier overlap (short or long
    docstring), then — only if that stays silent — operator-synonym overlap
    against the body's operations. This function is also CM307's tier-1
    gate (see ``semantic_restatement._semantic_candidate``), so widening any
    check here automatically narrows CM307's scope too, keeping the two
    rules from ever double-reporting the same paraphrase.
    """
    docstring = ast.get_docstring(owner.node, clean=True)
    node = docstring_node(owner.node)
    if docstring is None or node is None:
        return None
    text = docstring.strip()
    if not text:
        return None
    reason = (
        _short_docstring_reason(text, owner.short_reference, thresholds.signature)
        if len(text.splitlines()) <= 2
        else _long_docstring_reason(text, owner.reference)
    )
    if reason is None:
        reason = _operator_paraphrase_reason(text, owner.operator_words, thresholds.body_overlap)
    return (node, reason) if reason is not None else None


class DocstringRestatesName(Rule):
    id = "CM301"
    name = "docstring-restates-name"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.6, "private_overlap": 0.35, "body_overlap": 0.6}
    description = (
        "Flags docstrings that say nothing beyond the signature: a short one "
        '(`def get_user_name`: """Gets the user name.""") whose words all come from '
        "the function/class name and parameters, or a longer one where every line "
        "stays within that same vocabulary plus generic filler nouns. A `_`-prefixed "
        "(private) name is judged at the much stricter `private_overlap` — it has no "
        "external reader to write prose for, only its own body, which the reader can "
        "just read instead. Also flags a function docstring whose words are mostly "
        "synonyms of its body's operators/keywords (`\"\"\"Adds two numbers and returns "
        'the sum."""` over `return a + b`), reusing CM302\'s operator-synonym table '
        "against the whole body instead of one annotated line, at `body_overlap`. "
        "Why-signal docstrings are exempt from this check, same as CM302."
    )
    guidance = (
        "Only write a docstring if it says something the signature can't — skip it, "
        "or document why/edge cases/units/invariants, not a restatement of the name. "
        "Hold a private helper to a much stricter bar than a public function: its only "
        "reader can already see the body, so the docstring must earn its place."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        overlap_threshold = ctx.config.options["overlap"]
        private_overlap_threshold = ctx.config.options["private_overlap"]
        body_overlap_threshold = ctx.config.options["body_overlap"]
        for owner in _owners(ctx):
            signature_threshold = private_overlap_threshold if is_private(owner.name) else overlap_threshold
            thresholds = _OverlapThresholds(signature_threshold, body_overlap_threshold)
            yield from self._check_owner(ctx, owner, thresholds)

    def _check_owner(
        self, ctx: FileContext, owner: _DocstringOwner, thresholds: _OverlapThresholds
    ) -> Iterable[Violation]:
        found = _restatement(owner, thresholds)
        if found is None:
            return
        node, reason = found
        yield self.violation(
            ctx,
            node,
            ViolationDetails(
                message=f"docstring of `{owner.name}` {reason}",
                suggestion=(
                    "delete it, or document what the name cannot say: why, edge cases, "
                    "units, invariants"
                ),
                symbol=owner.name,
            ),
        )


class BoilerplateParamDocs(Rule):
    id = "CM304"
    name = "boilerplate-param-docs"
    default_severity = Severity.WARNING
    default_options = {"min_uninformative": 0.5}
    description = (
        "Flags Google-style Args:/Returns: sections where entries like "
        "`data: The data.` describe nothing beyond the parameter name."
    )
    guidance = (
        "In an Args:/Returns: docstring section, document only parameters whose "
        "meaning, units, or constraints aren't obvious from the name — skip entries "
        "like `data: The data.`"
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        min_uninformative = ctx.config.options["min_uninformative"]
        for function in ctx.functions:
            docstring = ast.get_docstring(function, clean=True)
            node = docstring_node(function)
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
        """Score each Args/Returns/Yields/Raises line against what it ought to explain.

        A Returns/Raises/Yields entry describes the *output*, so it's judged
        against the function's own name (there's no parameter to fall back
        on); every other section judges an entry against its own parameter
        name. Text outside a recognized section, or that doesn't parse as a
        `name: description` line, is skipped rather than guessed at.
        """
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
            uninformative = desc_words <= (reference | GENERIC_PARAM_WORDS)
            yield name, uninformative
