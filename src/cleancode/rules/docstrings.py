"""Docstring noise rules (CM301, CM304, CM307).

CM301/CM304 deterministically detect the classic LLM docstring padding: a
docstring that restates the signature, and Args sections that document
nothing. The core trick is word-overlap between the natural-language text
and the identifiers it describes. CM307 is the semantic second tier for the
paraphrases word-overlap cannot see — see ``cleancode.semantics``.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from cleancode.models import Comment, FileContext, Severity, Violation, ViolationDetails
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
from cleancode.rules.comments import is_exempt, lexically_restates_code

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
    """

    node: FunctionNode | ast.ClassDef
    name: str
    reference: set[str]
    short_reference: set[str]


def _owners(ctx: FileContext) -> Iterator[_DocstringOwner]:
    for function in ctx.functions:
        signature = _signature_words(function)
        body_words = _body_source_words(function, ctx.lines)
        yield _DocstringOwner(function, function.name, signature, signature | body_words)
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.ClassDef):
            reference = _class_reference_words(node)
            yield _DocstringOwner(node, node.name, reference, reference)


def _restatement(
    owner: "_DocstringOwner", overlap_threshold: float
) -> tuple[ast.Constant, str] | None:
    docstring = ast.get_docstring(owner.node, clean=True)
    node = docstring_node(owner.node)
    if docstring is None or node is None:
        return None
    text = docstring.strip()
    if not text:
        return None
    reason = (
        _short_docstring_reason(text, owner.short_reference, overlap_threshold)
        if len(text.splitlines()) <= 2
        else _long_docstring_reason(text, owner.reference)
    )
    return (node, reason) if reason is not None else None


class DocstringRestatesName(Rule):
    id = "CM301"
    name = "docstring-restates-name"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.6, "private_overlap": 0.35}
    description = (
        "Flags docstrings that say nothing beyond the signature: a short one "
        '(`def get_user_name`: """Gets the user name.""") whose words all come from '
        "the function/class name and parameters, or a longer one where every line "
        "stays within that same vocabulary plus generic filler nouns. A `_`-prefixed "
        "(private) name is judged at the much stricter `private_overlap` — it has no "
        "external reader to write prose for, only its own body, which the reader can "
        "just read instead."
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
        for owner in _owners(ctx):
            threshold = private_overlap_threshold if is_private(owner.name) else overlap_threshold
            yield from self._check_owner(ctx, owner, threshold)

    def _check_owner(
        self, ctx: FileContext, owner: _DocstringOwner, overlap_threshold: float
    ) -> Iterable[Violation]:
        found = _restatement(owner, overlap_threshold)
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


def _standalone_comment_blocks(ctx: FileContext) -> Iterator[list[Comment]]:
    """Runs of adjacent same-column standalone comments — the paragraph a reader sees.

    A wrapped comment is one thought split across ``#`` lines; judging the
    lines separately would strip each fragment of the context (often the
    rationale) carried by its neighbors.
    """
    block: list[Comment] = []
    for comment in ctx.comments:
        if comment.inline:
            continue
        if block and comment.lineno == block[-1].lineno + 1 and comment.col_offset == block[0].col_offset:
            block.append(comment)
            continue
        if block:
            yield block
        block = [comment]
    if block:
        yield block


def _semantic_candidate(
    function: FunctionNode, ctx: FileContext, max_lines: int
) -> tuple[ast.Constant, str] | None:
    """The docstring ``CM307`` should judge on ``function``, or ``None``.

    Decorated functions are out of scope (property/click/fixture docstrings
    are framework-facing help text), as is anything ``CM301`` at default
    thresholds already catches — the deterministic tier stays first and no
    docstring is ever reported by both rules.
    """
    docstring = ast.get_docstring(function, clean=True)
    node = docstring_node(function)
    if function.decorator_list or docstring is None or node is None:
        return None
    text = docstring.strip()
    if not text or len(text.splitlines()) > max_lines:
        return None
    signature = _signature_words(function)
    owner = _DocstringOwner(
        function, function.name, signature, signature | _body_source_words(function, ctx.lines)
    )
    cm301_options = DocstringRestatesName.default_options
    lexical_threshold = (
        cm301_options["private_overlap"] if is_private(function.name) else cm301_options["overlap"]
    )
    return None if _restatement(owner, lexical_threshold) is not None else (node, text)


def _judgeable_text(text: str, min_words: int) -> bool:
    """Cheap pre-filters shared by CM307's docstring and comment paths.

    A why-signal word anywhere exempts the whole text — same short-circuit
    ``CM302`` uses — and texts with too few content words carry too little
    signal to judge semantically.
    """
    words = content_words(text)
    if len(words) < min_words:
        return False
    return not (stemmed(words) & WHY_SIGNALS)


class SemanticRestatement(Rule):
    id = "CM307"
    name = "docstring-semantic-restatement"
    default_severity = Severity.WARNING
    default_options = {"threshold": 0.75, "min_words": 3, "max_lines": 3}
    description = (
        "Flags docstrings and standalone comments that only *narrate* what the "
        'code does, even when reworded with synonyms ("""Adds two numbers and '
        'returns the sum.""" over `return a + b`) — paraphrases the lexical '
        "rules (CM301/CM302) structurally cannot see. Each clause is scored by "
        "a small pretrained-embedding classifier (see `cleancode.semantics`); "
        "a text is flagged only when *every* clause reads as procedural "
        "description, so mixed comments that also carry rationale "
        '("... to maximize L1 cache hits") always pass. Scope is deliberately '
        "narrow: plain (undecorated) function docstrings of at most `max_lines` "
        "lines — a class docstring states responsibility and a decorated "
        "function's is framework-facing help text — and whole standalone "
        "comment blocks. Texts CM301/CM302 already flag, TODO/directive "
        "comments, and why-signal carriers are skipped."
    )
    guidance = (
        "Never narrate what code does in a docstring/comment, even reworded in "
        "synonyms — give rationale, constraints, units, or edge cases instead."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        yield from self._check_docstrings(ctx)
        yield from self._check_comments(ctx)

    def _check_docstrings(self, ctx: FileContext) -> Iterable[Violation]:
        max_lines = ctx.config.options["max_lines"]
        for function in ctx.functions:
            found = _semantic_candidate(function, ctx, max_lines)
            if found is None:
                continue
            node, text = found
            if self._purely_procedural(ctx, text):
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"docstring of `{function.name}` only narrates what the code does",
                        suggestion=(
                            "delete it, or say what the code cannot: rationale, "
                            "constraints, units, edge cases"
                        ),
                        symbol=function.name,
                    ),
                )

    def _check_comments(self, ctx: FileContext) -> Iterable[Violation]:
        for block in _standalone_comment_blocks(ctx):
            if any(is_exempt(comment) for comment in block):
                continue
            if any(lexically_restates_code(ctx, comment) for comment in block):
                continue  # CM302's catch — the deterministic tier stays first
            text = " ".join(comment.text for comment in block)
            if self._purely_procedural(ctx, text):
                yield self.violation(
                    ctx,
                    block[0],
                    ViolationDetails(
                        message=f"comment only narrates what the code does: `# {text}`",
                        suggestion="delete it, or say why instead of what",
                    ),
                )

    def _purely_procedural(self, ctx: FileContext, text: str) -> bool:
        """True when every clause of ``text`` reads as procedural narration.

        A clause must be narration-shaped (verb-led) *and* score procedural
        to count. One clause that isn't — a rationale, a noun-led value
        contract, or one the classifier cannot judge — clears the whole
        text: for a linter, a missed paraphrase is far cheaper than flagging
        a comment that carries real information.
        """
        if not _judgeable_text(text, ctx.config.options["min_words"]):
            return False
        # Imported here so the embedding table only loads once a judgeable
        # candidate exists, keeping `clean-code` startup free of the cost.
        from cleancode.semantics.classifier import load_classifier
        from cleancode.semantics.clauses import clauses, narration_shaped

        classifier = load_classifier()
        threshold = ctx.config.options["threshold"]
        parts = clauses(text)
        return bool(parts) and all(
            narration_shaped(clause)
            and (score := classifier.score(clause)) is not None
            and score >= threshold
            for clause in parts
        )
