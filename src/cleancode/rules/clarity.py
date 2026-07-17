"""Expression clarity rules (SM614–SM617).

Size limits alone (ST1xx) can be satisfied by compressing logic into denser
expressions: a nested loop becomes a ternary picking a mutation target, a
counter hides a boolean cast, logic disappears behind ``functools.partial``.
These rules catch that compression, so generated code stays readable for a
human reviewer instead of merely passing the structural gates.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, own_scope_walk


class BoolArithmetic(Rule):
    id = "SM614"
    name = "bool-arithmetic"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags an augmented assignment whose right-hand side is a bare comparison "
        "or membership test (`count += value in seen`) — a boolean used as a number "
        "makes the reader do the int-cast in their head. Deliberately narrow "
        "(augmented assignments only), so numpy/torch mask arithmetic is untouched."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if isinstance(node, ast.AugAssign) and isinstance(node.value, ast.Compare):
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message="augmented assignment adds a boolean condition as a number",
                        suggestion="make the count explicit: `if <condition>: counter += 1`",
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


def _contains_nested_ternary(ternary: ast.IfExp) -> bool:
    return any(
        isinstance(inner, ast.IfExp) for inner in ast.walk(ternary) if inner is not ternary
    )


def _inside_ternary(node: ast.AST) -> bool:
    """True when ``node`` sits inside another ternary of the same statement."""
    current = getattr(node, "parent", None)
    while current is not None and not isinstance(current, ast.stmt):
        if isinstance(current, ast.IfExp):
            return True
        current = getattr(current, "parent", None)
    return False


class NestedTernary(Rule):
    id = "SM615"
    name = "nested-ternary"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a conditional expression nested inside another conditional expression "
        "(`a if x else (b if y else c)`). One ternary reads fine; two levels always "
        "need a second pass. Only the outermost ternary of a chain is reported."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if not isinstance(node, ast.IfExp) or _inside_ternary(node):
                continue
            if _contains_nested_ternary(node):
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message="ternary expression nested inside another ternary",
                        suggestion="unfold into an if/elif statement or a dict lookup",
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


@dataclass(frozen=True)
class _ModuleCallables:
    """Names in one module that a returned expression could resolve to."""

    functions: frozenset[str]
    partial_bindings: frozenset[str]  # bound by `from functools import partial [as p]`
    functools_aliases: frozenset[str]  # bound by `import functools [as ft]`


def _bound_names(node: ast.Import | ast.ImportFrom, source_name: str) -> list[str]:
    """The names one import statement binds for the alias originally called ``source_name``."""
    return [alias.asname or alias.name for alias in node.names if alias.name == source_name]


def _module_callables(ctx: FileContext) -> _ModuleCallables:
    partial_bindings: set[str] = set()
    functools_aliases: set[str] = set()
    for node in ast.walk(ctx.tree):
        if isinstance(node, ast.ImportFrom) and node.module == "functools":
            partial_bindings.update(_bound_names(node, "partial"))
        elif isinstance(node, ast.Import):
            functools_aliases.update(_bound_names(node, "functools"))
    return _ModuleCallables(
        functions=frozenset(function.name for function in ctx.functions),
        partial_bindings=frozenset(partial_bindings),
        functools_aliases=frozenset(functools_aliases),
    )


def _is_partial_call(node: ast.expr, callables: _ModuleCallables) -> bool:
    """True only for calls that resolve to ``functools.partial`` through this module's imports.

    Matching the bare attribute name would misfire on any unrelated
    ``something.partial(...)`` method and claim it is a ``functools.partial``.
    """
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in callables.partial_bindings
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "partial"
        and isinstance(func.value, ast.Name)
        and func.value.id in callables.functools_aliases
    )


class CallableIndirection(Rule):
    id = "SM616"
    name = "callable-indirection"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a function that manufactures a callable instead of doing work: it "
        "returns a `lambda`, returns a `functools.partial(...)`, or its whole body "
        "is `return <name of another function>`. Each is a hop the reviewer must "
        "chase to find the actual logic. Returning a nested `def` is not flagged — "
        "that's the decorator shape."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        callables = _module_callables(ctx)
        for function in ctx.functions:
            yield from self._check_function(ctx, function, callables)

    def _check_function(
        self, ctx: FileContext, function: FunctionNode, callables: _ModuleCallables
    ) -> Iterator[Violation]:
        for statement in own_scope_walk(function):
            if not isinstance(statement, ast.Return) or statement.value is None:
                continue
            reason = self._indirection_reason(function, statement, callables)
            if reason is None:
                continue
            yield self.violation(
                ctx,
                statement,
                ViolationDetails(
                    message=f"`{function.name}` {reason}",
                    suggestion=(
                        "define a plain function and pass it the data it needs, "
                        "instead of manufacturing a callable"
                    ),
                    symbol=function.name,
                ),
            )

    def _indirection_reason(
        self, function: FunctionNode, statement: ast.Return, callables: _ModuleCallables
    ) -> str | None:
        value = statement.value
        if isinstance(value, ast.Lambda):
            return "returns a lambda"
        if _is_partial_call(value, callables):
            return "returns a `functools.partial`"
        forwards = self._is_bare_forward(function, statement, callables)
        return f"does nothing but hand back `{value.id}`" if forwards else None  # type: ignore[union-attr]

    @staticmethod
    def _is_bare_forward(
        function: FunctionNode, statement: ast.Return, callables: _ModuleCallables
    ) -> bool:
        """True when the function's whole body is this very ``return <function name>``.

        Identity against the top-level body matters: a return nested inside a
        guard ``if`` is conditional dispatch with a ``None`` fallthrough, not
        a bare forward.
        """
        value = statement.value
        if not (isinstance(value, ast.Name) and value.id in callables.functions):
            return False
        body = function.body
        if body and _is_docstring(body[0]):
            body = body[1:]
        return body == [statement]


def _is_docstring(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


# One nesting level per node that makes the reader push a mental stack frame.
_DEPTH_NODES = (
    ast.Call,
    ast.BinOp,
    ast.IfExp,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.JoinedStr,
    ast.Await,
)

# Statements whose subtree contains further statements; those inner statements
# are measured on their own, so measuring the container would double-report.
_COMPOUND_STATEMENTS = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.Match,
)


def _expression_depth(node: ast.AST, depth: int = 0) -> int:
    """Deepest chain of nested operation nodes under (and including) ``node``."""
    if isinstance(node, _DEPTH_NODES):
        depth += 1
    children = list(ast.iter_child_nodes(node))
    if not children:
        return depth
    return max(_expression_depth(child, depth) for child in children)


class DeepExpression(Rule):
    id = "SM617"
    name = "deep-expression"
    default_severity = Severity.WARNING
    default_options = {"max_depth": 4}
    description = (
        "Flags a statement whose expression tree nests operations (calls, arithmetic, "
        "ternaries, comprehensions, f-strings) deeper than `max_depth` (default 4). "
        "A flat chain of conditions reads fine at any length; five layers of "
        "calls-inside-f-strings-inside-comprehensions on one line do not. Module-level "
        "statements (constant tables) are exempt. Complements ST101, which limits "
        "statement nesting rather than expression nesting."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_depth = ctx.config.options["max_depth"]
        for function in ctx.functions:
            yield from self._check_function(ctx, function, max_depth)

    def _check_function(
        self, ctx: FileContext, function: FunctionNode, max_depth: int
    ) -> Iterator[Violation]:
        for statement in own_scope_walk(function):
            if not isinstance(statement, ast.stmt) or isinstance(statement, _COMPOUND_STATEMENTS):
                continue
            depth = _expression_depth(statement)
            if depth > max_depth:
                yield self.violation(
                    ctx,
                    statement,
                    ViolationDetails(
                        message=f"statement nests expressions {depth} deep "
                        f"(maximum {max_depth})",
                        suggestion="pull the inner calls out into named intermediate variables",
                        symbol=ctx.enclosing_symbol(statement),
                    ),
                )
