"""Structural rules: nesting depth, size limits, and cyclomatic complexity (ST1xx)."""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import (
    FunctionNode,
    Rule,
    functions,
    is_dunder,
    is_elif_branch,
    own_scope_walk,
    split_identifier,
)

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


def _enclosing_function(node: ast.AST) -> FunctionNode | None:
    """The nearest function that ``node`` is nested inside, if any."""
    current = getattr(node, "parent", None)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = getattr(current, "parent", None)
    return None


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
        for function in functions(ctx.tree):
            if _enclosing_function(function) is not None:
                continue  # measured by the outermost function, depth inherited (not reset)
            deepest, first_offender = self._measure(function, max_depth)
            if first_offender is not None:
                yield self.violation(
                    ctx,
                    first_offender,
                    ViolationDetails(
                        message=f"nesting depth {deepest} exceeds the maximum of {max_depth}",
                        suggestion=(
                            "extract the inner block into a well-named helper function, or "
                            "flatten with early returns / guard clauses"
                        ),
                        symbol=ctx.enclosing_symbol(function.body[0]) or function.name,
                    ),
                )

    def _measure(
        self, function: FunctionNode, max_depth: int
    ) -> tuple[int, ast.AST | None]:
        deepest = 0
        first_offender: ast.AST | None = None

        def walk(statement: ast.stmt, depth: int) -> None:
            nonlocal deepest, first_offender
            if isinstance(statement, _NESTING_NODES) and not is_elif_branch(statement):
                depth += 1
                deepest = max(deepest, depth)
                if depth > max_depth and first_offender is None:
                    # a match_case carries no position of its own; anchor at its pattern
                    first_offender = (
                        statement.pattern if isinstance(statement, ast.match_case) else statement
                    )
            for child in _body_statements(statement):
                walk(child, depth)

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
                    node,
                    ViolationDetails(
                        message=f"{self.block_kind} `{node.name}` is {length} lines long "
                        f"(maximum {max_lines})",
                        suggestion=self.suggestion,
                        symbol=node.name,
                    ),
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
        for function in functions(ctx.tree):
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
                    function,
                    ViolationDetails(
                        message=f"function `{function.name}` takes {len(parameters)} parameters "
                        f"(maximum {max_params})",
                        suggestion="group related parameters into a dataclass or config object",
                        symbol=function.name,
                    ),
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
        for function in functions(ctx.tree):
            complexity = self._complexity(function)
            if complexity > max_complexity:
                yield self.violation(
                    ctx,
                    function,
                    ViolationDetails(
                        message=f"function `{function.name}` has cyclomatic complexity {complexity} "
                        f"(maximum {max_complexity})",
                        suggestion=(
                            "extract decision-heavy blocks into helpers or replace branch "
                            "chains with a dispatch dict / early returns"
                        ),
                        symbol=function.name,
                    ),
                )

    # Lambdas stay in the walk: they never get their own per-function score,
    # so their branches must count toward the enclosing function.
    _SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

    @classmethod
    def _complexity(cls, function: FunctionNode) -> int:
        complexity = 1
        for node in own_scope_walk(function, boundaries=cls._SCOPE_BOUNDARIES):
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


class DoOneThing(Rule):
    id = "ST106"
    name = "do-one-thing"
    default_severity = Severity.WARNING
    default_options = {
        "conjunctions": ["and", "or"],
        "allowed_names": [],
    }
    description = (
        "Flags functions whose name joins responsibilities with a conjunction "
        "(`load_and_save`, `fetch_or_default`). Needing 'and'/'or' to name a "
        "function is a sign it does more than one thing — split it."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        conjunctions = set(ctx.config.options["conjunctions"])
        allowed = set(ctx.config.options["allowed_names"])
        for function in functions(ctx.tree):
            word = self._conjunction(function, conjunctions, allowed)
            if word is not None:
                yield self.violation(
                    ctx,
                    function,
                    ViolationDetails(
                        message=f"function `{function.name}` joins responsibilities with "
                        f"`{word}`; a function should do one thing",
                        suggestion=(
                            "split into separate, single-purpose functions — one for each "
                            "part of the name — and let the caller compose them"
                        ),
                        symbol=function.name,
                    ),
                )

    @staticmethod
    def _conjunction(
        function: FunctionNode, conjunctions: set[str], allowed: set[str]
    ) -> str | None:
        if function.name in allowed or is_dunder(function.name):
            return None
        joined = sorted(conjunctions.intersection(split_identifier(function.name)))
        return joined[0] if joined else None


_GUARD_EXIT_TYPES = (ast.Continue, ast.Return, ast.Raise, ast.Break)


def _is_guard_clause(statement: ast.stmt) -> bool:
    """An `if` with no `else` whose entire body is a single control-flow exit."""
    return (
        isinstance(statement, ast.If)
        and not statement.orelse
        and len(statement.body) == 1
        and isinstance(statement.body[0], _GUARD_EXIT_TYPES)
    )


def _blocks(function: FunctionNode) -> Iterator[list[ast.stmt]]:
    """Every statement list nested directly inside ``function``, one per scope.

    A block is the function body itself, or the body/orelse/finalbody/except/
    match-case of any statement within it. Nested function and class
    definitions are skipped — they are examined on their own.
    """

    def walk(statements: list[ast.stmt]) -> Iterator[list[ast.stmt]]:
        yield statements
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for child_block in _child_blocks(statement):
                yield from walk(child_block)

    yield from walk(function.body)


def _child_blocks(statement: ast.stmt) -> Iterator[list[ast.stmt]]:
    """The body/orelse/finalbody/handler/case statement-lists of one statement."""
    for attr in ("body", "orelse", "finalbody"):
        block = getattr(statement, attr, None)
        if block:
            yield block
    for handler in getattr(statement, "handlers", []):
        yield handler.body
    for case in getattr(statement, "cases", []):
        yield case.body


class TooManyGuardClauses(Rule):
    id = "ST107"
    name = "too-many-guard-clauses"
    default_severity = Severity.INFO
    default_options = {"max_guards": 2}
    description = (
        "Flags a function where one block strings together more than `max_guards` "
        "sequential guard clauses (`if cond: continue/return/raise/break`) ahead of "
        "the real work. Filtering piled up next to a decision is a 'more than one "
        "thing' smell (see ST106): split the eligibility checks into their own "
        "filter/predicate function and the remaining logic into another."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_guards = ctx.config.options["max_guards"]
        for function in functions(ctx.tree):
            count = self._max_guard_count(function)
            if count > max_guards:
                yield self.violation(
                    ctx,
                    function,
                    ViolationDetails(
                        message=f"function `{function.name}` strings together {count} sequential "
                        f"guard clauses in one block (maximum {max_guards})",
                        suggestion=(
                            "extract the guard checks into a single named filter/predicate "
                            "function, and move the remaining logic into its own function — "
                            "so each piece does exactly one thing"
                        ),
                        symbol=function.name,
                    ),
                )

    @staticmethod
    def _max_guard_count(function: FunctionNode) -> int:
        return max(
            (
                sum(1 for statement in block if _is_guard_clause(statement))
                for block in _blocks(function)
            ),
            default=0,
        )
