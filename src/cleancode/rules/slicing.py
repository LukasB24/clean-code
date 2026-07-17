"""Tensor/array subscript complexity rules (SL4xx).

LLM-generated numerical code loves one-liners like
``out = x[:, None, idx[i+1]:idx[i+2]:2, ::-1]``. These rules score subscript
expressions and push complex indexing into named intermediate steps.
"""

from __future__ import annotations

import ast
from typing import Callable, Iterable

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import Rule


def _is_chain_head(node: ast.Subscript) -> bool:
    parent = getattr(node, "parent", None)
    return not (isinstance(parent, ast.Subscript) and parent.value is node)


def _in_annotation(node: ast.Subscript) -> bool:
    """True for subscripts used as type annotations (``dict[str, int]`` generics)."""
    child: ast.AST = node
    parent = getattr(node, "parent", None)
    while parent is not None:
        if _is_annotation_slot(parent, child):
            return True
        if _ends_annotation_search(parent):
            return False
        child = parent
        parent = getattr(parent, "parent", None)
    return False


def _is_annotation_slot(parent: ast.AST, child: ast.AST) -> bool:
    if isinstance(parent, (ast.AnnAssign, ast.arg)):
        return child is parent.annotation
    if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return child is parent.returns
    return False


def _ends_annotation_search(parent: ast.AST) -> bool:
    """True when ``parent`` proves the walk has left any annotation it started in."""
    return isinstance(parent, ast.stmt) and not isinstance(parent, ast.AnnAssign)


def _index_features(index: ast.expr) -> tuple[int, list[str]]:
    """Score one subscript's index expression and describe what drove the score."""
    dimensions = len(index.elts) if isinstance(index, ast.Tuple) else 1
    score = dimensions
    reasons = [f"{dimensions} dimensions"] if dimensions > 1 else []

    negative_steps: set[ast.AST] = set()
    for node in ast.walk(index):
        feature = _score_node(node, negative_steps)
        if feature is not None:
            points, labels = feature
            score += points
            reasons.extend(labels)
    return score, reasons


def _score_node(node: ast.AST, negative_steps: set[ast.AST]) -> tuple[int, list[str]] | None:
    scorer = _NODE_SCORERS.get(type(node))
    return scorer(node, negative_steps) if scorer else None


def _score_slice_step(
    node: ast.Slice, negative_steps: set[ast.AST]
) -> tuple[int, list[str]] | None:
    if node.step is None:
        return None
    if _is_negative(node.step):
        negative_steps.add(node.step)
        return 2, ["explicit step", "negative step"]
    return 1, ["explicit step"]


def _score_constant(node: ast.Constant) -> tuple[int, list[str]] | None:
    if node.value is None:
        return 1, ["None/newaxis"]
    if node.value is Ellipsis:
        return 1, ["ellipsis"]
    return None


def _score_unary(
    node: ast.UnaryOp, negative_steps: set[ast.AST]
) -> tuple[int, list[str]] | None:
    if _is_negative(node) and node not in negative_steps:
        return 1, ["negative index"]
    return None


def _is_negative(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
    )


Scorer = Callable[[ast.AST, "set[ast.AST]"], "tuple[int, list[str]] | None"]

_NODE_SCORERS: dict[type, Scorer] = {
    ast.Slice: _score_slice_step,
    ast.Constant: lambda node, _steps: _score_constant(node),
    ast.UnaryOp: _score_unary,
    ast.BinOp: lambda node, _steps: (1, ["arithmetic in index"]),
    ast.Subscript: lambda node, _steps: (2, ["nested subscript"]),
    ast.Call: lambda node, _steps: (1, ["function call in index"]),
}


class ComplexSubscript(Rule):
    id = "SL401"
    name = "complex-subscript"
    default_severity = Severity.WARNING
    default_options = {"max_score": 5}
    description = (
        "Scores each subscript expression (+1 per dimension/step/None/ellipsis/"
        "negative index/arithmetic/call, +2 per nested subscript, negative steps "
        "count double) and flags scores above the threshold."
    )
    guidance = (
        "Name the index expressions of a complex subscript (multiple dimensions, "
        "steps, negative indices, nested calls) instead of writing one dense "
        "one-liner."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_score = ctx.config.options["max_score"]
        for node in ast.walk(ctx.tree):
            if isinstance(node, ast.Subscript) and self._is_scoreable(node):
                yield from self._check_subscript(ctx, node, max_score)

    @staticmethod
    def _is_scoreable(node: ast.Subscript) -> bool:
        """True for a subscript that should be scored on its own.

        Type annotations like ``dict[str, int]`` aren't slicing, and a subscript
        nested inside another's index is already counted there (+2).
        """
        return (
            _is_chain_head(node)
            and not _in_annotation(node)
            and not _nested_in_another_index(node)
        )

    def _check_subscript(
        self, ctx: FileContext, node: ast.Subscript, max_score: int
    ) -> Iterable[Violation]:
        score, reasons = self._chain_score(node)
        if score <= max_score:
            return
        snippet = ast.get_source_segment(ctx.source, node) or "<subscript>"
        summary = ", ".join(sorted(set(reasons)))
        yield self.violation(
            ctx,
            node,
            ViolationDetails(
                message=f"subscript `{snippet}` has complexity {score} "
                f"(maximum {max_score}): {summary}",
                suggestion=(
                    "name the index expressions (`window = slice(start, stop, 2)`) "
                    "or build the result in intermediate, well-named slices"
                ),
                symbol=ctx.enclosing_symbol(node),
            ),
        )

    def _chain_score(self, node: ast.Subscript) -> tuple[int, list[str]]:
        score, reasons = _index_features(node.slice)
        if isinstance(node.value, ast.Subscript):
            inner_score, inner_reasons = self._chain_score(node.value)
            score += inner_score
            reasons += inner_reasons
        return score, reasons


def _nested_in_another_index(node: ast.Subscript) -> bool:
    child: ast.AST = node
    parent = getattr(node, "parent", None)
    while parent is not None and not isinstance(parent, ast.stmt):
        if isinstance(parent, ast.Subscript) and child is parent.slice:
            return True
        child = parent
        parent = getattr(parent, "parent", None)
    return False


class ChainedSubscript(Rule):
    id = "SL402"
    name = "chained-subscript"
    default_severity = Severity.WARNING
    default_options = {"max_chain": 2}
    description = (
        "Flags subscript chains like `grid[i][j][k]`; bind intermediates to names "
        "or use multi-dimensional indexing `grid[i, j, k]`."
    )
    guidance = (
        "Bind intermediate lookups to named variables instead of chaining "
        "subscripts more than {max_chain} deep (`grid[i][j][k]`) — or use "
        "multi-dimensional indexing."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_chain = ctx.config.options["max_chain"]
        for node in ast.walk(ctx.tree):
            if not isinstance(node, ast.Subscript) or not _is_chain_head(node):
                continue
            if _in_annotation(node):
                continue
            length = self._chain_length(node)
            if length > max_chain:
                snippet = ast.get_source_segment(ctx.source, node) or "<subscript>"
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"subscript chain `{snippet}` is {length} levels deep "
                        f"(maximum {max_chain})",
                        suggestion=(
                            "bind intermediate lookups to named variables "
                            "(`row = grid[i]`) or use `grid[i, j, k]` for arrays"
                        ),
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )

    def _chain_length(self, node: ast.Subscript) -> int:
        length = 0
        current: ast.expr = node
        while isinstance(current, ast.Subscript):
            length += 1
            current = current.value
        return length
