"""Structural rules: nesting depth, size limits, and cyclomatic complexity (ST1xx)."""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation
from cleancode.rules.base import Rule

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.match_case,
)


def _is_elif(statement: ast.stmt) -> bool:
    """True for the `elif` branches of an if-chain, which the AST nests in orelse.

    A hand-written `else:\\n    if ...` sits one indent deeper, so the column
    offset distinguishes it from `elif` (which shares the parent's column).
    """
    parent = getattr(statement, "parent", None)
    return (
        isinstance(statement, ast.If)
        and isinstance(parent, ast.If)
        and parent.orelse == [statement]
        and statement.col_offset == parent.col_offset
    )


def _functions(tree: ast.Module) -> Iterator[FunctionNode]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _body_statements(node: ast.AST) -> Iterator[ast.stmt]:
    """Direct child statements of a block node, across all its clauses."""
    for clause in ("body", "orelse", "finalbody", "handlers", "cases"):
        for child in getattr(node, clause, []):
            yield from _clause_statements(child)


def _clause_statements(child: ast.AST) -> Iterator[ast.stmt]:
    """Normalize one clause child into the statements that nest under it."""
    if isinstance(child, ast.ExceptHandler):
        yield from child.body
    elif isinstance(child, ast.match_case):
        yield child  # match_case itself nests; its body is walked below
    elif isinstance(child, ast.stmt):
        yield child


class MaxNestingDepth(Rule):
    id = "ST101"
    name = "max-nesting-depth"
    default_severity = Severity.ERROR
    default_options = {"max_depth": 2}
    description = (
        "Limits how deeply loops, conditionals, `with`, and `try` blocks nest inside a "
        "function. Deep nesting is the hallmark of hard-to-review generated code."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_depth = ctx.config.options["max_depth"]
        for function in _functions(ctx.tree):
            deepest, first_offender = self._measure(function, max_depth)
            if first_offender is not None:
                yield self.violation(
                    ctx,
                    f"nesting depth {deepest} exceeds the maximum of {max_depth}",
                    line=first_offender.lineno,
                    col=first_offender.col_offset,
                    suggestion=(
                        "extract the inner block into a well-named helper function, or "
                        "flatten with early returns / guard clauses"
                    ),
                    symbol=ctx.enclosing_symbol(function.body[0]) or function.name,
                )

    def _measure(
        self, function: FunctionNode, max_depth: int
    ) -> tuple[int, ast.AST | None]:
        deepest = 0
        first_offender: ast.AST | None = None

        def walk(statement: ast.stmt, depth: int) -> None:
            nonlocal deepest, first_offender
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return  # nested functions are measured on their own
            if isinstance(statement, _NESTING_NODES) and not _is_elif(statement):
                depth += 1
                deepest = max(deepest, depth)
                if depth > max_depth and first_offender is None:
                    first_offender = statement
            for child in _body_statements(statement):
                walk(child, depth)
            for case in getattr(statement, "cases", []):
                for child in case.body:
                    walk(child, depth + 1)

        for statement in function.body:
            walk(statement, 0)
        return deepest, first_offender


class _MaxBlockLength(Rule):
    """Shared implementation for function and class length limits."""

    node_types: tuple[type[ast.AST], ...] = ()
    block_kind = ""

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_lines = ctx.config.options["max_lines"]
        for node in ast.walk(ctx.tree):
            if not isinstance(node, self.node_types):
                continue
            length = (node.end_lineno or node.lineno) - node.lineno + 1
            if length > max_lines:
                yield self.violation(
                    ctx,
                    f"{self.block_kind} `{node.name}` is {length} lines long "
                    f"(maximum {max_lines})",
                    line=node.lineno,
                    col=node.col_offset,
                    suggestion=self.suggestion,
                    symbol=node.name,
                )


class MaxFunctionLength(_MaxBlockLength):
    id = "ST102"
    name = "max-function-length"
    default_severity = Severity.WARNING
    default_options = {"max_lines": 60}
    description = "Limits function length (docstring included) so one function fits one screen."
    node_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    block_kind = "function"
    suggestion = "split the function into smaller, single-purpose helpers"


class MaxClassLength(_MaxBlockLength):
    id = "ST103"
    name = "max-class-length"
    default_severity = Severity.WARNING
    default_options = {"max_lines": 200}
    description = "Limits class length; god classes hide too many responsibilities."
    node_types = (ast.ClassDef,)
    block_kind = "class"
    suggestion = "split the class by responsibility, or move helpers to module level"


class MaxParameters(Rule):
    id = "ST104"
    name = "max-parameters"
    default_severity = Severity.WARNING
    default_options = {"max_params": 3}
    description = "Limits the number of function parameters (self/cls, *args, **kwargs excluded)."

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_params = ctx.config.options["max_params"]
        for function in _functions(ctx.tree):
            parameters = [
                *function.args.posonlyargs,
                *function.args.args,
                *function.args.kwonlyargs,
            ]
            if parameters and self._is_method(function) and parameters[0].arg in ("self", "cls"):
                parameters = parameters[1:]
            if len(parameters) > max_params:
                yield self.violation(
                    ctx,
                    f"function `{function.name}` takes {len(parameters)} parameters "
                    f"(maximum {max_params})",
                    line=function.lineno,
                    col=function.col_offset,
                    suggestion="group related parameters into a dataclass or config object",
                    symbol=function.name,
                )

    @staticmethod
    def _is_method(function: FunctionNode) -> bool:
        return isinstance(getattr(function, "parent", None), ast.ClassDef)


class MaxComplexity(Rule):
    id = "ST105"
    name = "max-complexity"
    default_severity = Severity.ERROR
    default_options = {"max_complexity": 10}
    description = (
        "Limits cyclomatic complexity per function: 1 + one per if/for/while/except/"
        "assert/ternary/match-case, per comprehension filter, and per extra and/or operand."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_complexity = ctx.config.options["max_complexity"]
        for function in _functions(ctx.tree):
            complexity = self._complexity(function)
            if complexity > max_complexity:
                yield self.violation(
                    ctx,
                    f"function `{function.name}` has cyclomatic complexity {complexity} "
                    f"(maximum {max_complexity})",
                    line=function.lineno,
                    col=function.col_offset,
                    suggestion=(
                        "extract decision-heavy blocks into helpers or replace branch "
                        "chains with a dispatch dict / early returns"
                    ),
                    symbol=function.name,
                )

    @staticmethod
    def _complexity(function: FunctionNode) -> int:
        complexity = 1
        for node in ast.walk(function):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not function:
                continue  # nested functions get their own score; skip their def node
            if isinstance(
                node,
                (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert, ast.match_case),
            ):
                complexity += 1
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1
            elif isinstance(node, ast.comprehension):
                complexity += len(node.ifs)
        return complexity
