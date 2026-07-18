"""Semantic docstring/comment restatement rule (CM307).

The second tier behind CM301/CM302's deterministic word-overlap checks: a
pretrained-embedding classifier (see ``cleancode.semantics``) scores clauses
that paraphrase code in synonyms rather than restating it verbatim. Split
into its own module so ``docstrings.py`` stays focused on CM301/CM304.
"""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import Comment, FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import WHY_SIGNALS, FunctionNode, Rule, content_words, docstring_node, is_private, stemmed
from cleancode.rules.comments import is_exempt, lexically_restates_code
from cleancode.rules.docstrings import (
    DocstringRestatesName,
    _body_source_words,
    _DocstringOwner,
    _function_operator_words,
    _OverlapThresholds,
    _restatement,
    _signature_words,
)


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
    thresholds already catches — signature/body-identifier overlap *and*
    operator-synonym body overlap, via the same ``_restatement`` gate CM301
    itself uses, so the deterministic tier stays first and no docstring is
    ever reported by both rules.
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
        function,
        function.name,
        signature,
        signature | _body_source_words(function, ctx.lines),
        _function_operator_words(function, ctx),
    )
    cm301_options = DocstringRestatesName.default_options
    lexical_threshold = (
        cm301_options["private_overlap"] if is_private(function.name) else cm301_options["overlap"]
    )
    thresholds = _OverlapThresholds(lexical_threshold, cm301_options["body_overlap"])
    already_covered = _restatement(owner, thresholds)
    return None if already_covered is not None else (node, text)


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
        "comment blocks. Texts CM301/CM302 already flag (including CM301's "
        "operator-synonym body-overlap check), TODO/directive comments, and "
        "why-signal carriers are skipped."
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
