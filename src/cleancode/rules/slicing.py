"""Tensor/array subscript complexity rules (SL4xx).

LLM-generated numerical code loves one-liners like
``out = x[:, None, idx[i+1]:idx[i+2]:2, ::-1]``. These rules score subscript
expressions and push complex indexing into named intermediate steps.
"""

from __future__ import annotations

import ast
from typing import Iterable

from cleancode.models import FileContext, Severity, Violation
from cleancode.rules.base import Rule


def _is_chain_head(node: ast.Subscript) -> bool:
    """True when ``node`` is not itself the ``.value`` of an enclosing subscript."""
    parent = getattr(node, "parent", None)
    return not (isinstance(parent, ast.Subscript) and parent.value is node)


def _in_annotation(node: ast.Subscript) -> bool:
    """True for subscripts used as type annotations (``dict[str, int]`` generics)."""
    child: ast.AST = node
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, (ast.AnnAssign, ast.arg)) and child is parent.annotation:
            return True
        if (
            isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef))
            and child is parent.returns
        ):
            return True
        if isinstance(parent, ast.stmt) and not isinstance(parent, ast.AnnAssign):
            return False
        child = parent
        parent = getattr(parent, "parent", None)
    return False


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
    if isinstance(node, ast.Slice):
        return _score_slice_step(node, negative_steps)
    if isinstance(node, ast.Constant):
        return _score_constant(node)
    if isinstance(node, ast.UnaryOp):
        if _is_negative(node) and node not in negative_steps:
            return 1, ["negative index"]
        return None
    if isinstance(node, ast.BinOp):
        return 1, ["arithmetic in index"]
    if isinstance(node, ast.Subscript):
        return 2, ["nested subscript"]
    if isinstance(node, ast.Call):
        return 1, ["function call in index"]
    return None


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


def _is_negative(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
    )


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

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_score = ctx.config.options["max_score"]
        for node in ast.walk(ctx.tree):
            if not isinstance(node, ast.Subscript) or not _is_chain_head(node):
                continue
            if _in_annotation(node):
                continue  # dict[str, int]-style generics are types, not slicing
            if _nested_in_another_index(node):
                continue  # already counted as +2 inside the outer subscript's score
            score, reasons = self._chain_score(node)
            if score > max_score:
                snippet = ast.get_source_segment(ctx.source, node) or "<subscript>"
                summary = ", ".join(sorted(set(reasons)))
                yield self.violation(
                    ctx,
                    f"subscript `{snippet}` has complexity {score} "
                    f"(maximum {max_score}): {summary}",
                    line=node.lineno,
                    col=node.col_offset,
                    suggestion=(
                        "name the index expressions (`window = slice(start, stop, 2)`) "
                        "or build the result in intermediate, well-named slices"
                    ),
                    symbol=ctx.enclosing_symbol(node),
                )

    def _chain_score(self, node: ast.Subscript) -> tuple[int, list[str]]:
        score, reasons = _index_features(node.slice)
        if isinstance(node.value, ast.Subscript):
            inner_score, inner_reasons = self._chain_score(node.value)
            score += inner_score
            reasons += inner_reasons
        return score, reasons


def _nested_in_another_index(node: ast.Subscript) -> bool:
    """True if this subscript lives inside an enclosing subscript's index."""
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
                    f"subscript chain `{snippet}` is {length} levels deep "
                    f"(maximum {max_chain})",
                    line=node.lineno,
                    col=node.col_offset,
                    suggestion=(
                        "bind intermediate lookups to named variables "
                        "(`row = grid[i]`) or use `grid[i, j, k]` for arrays"
                    ),
                    symbol=ctx.enclosing_symbol(node),
                )

    def _chain_length(self, node: ast.Subscript) -> int:
        length = 0
        current: ast.expr = node
        while isinstance(current, ast.Subscript):
            length += 1
            current = current.value
        return length
