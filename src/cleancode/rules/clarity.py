"""Expression clarity rules (SM614–SM619).

Size limits alone (ST1xx) can be satisfied by compressing logic into denser
expressions: a nested loop becomes a ternary picking a mutation target, a
counter hides a boolean cast, logic disappears behind ``functools.partial``
or an extra wrapper hop, a value fallback gets buried mid-expression.
These rules catch that compression, so generated code stays readable for a
human reviewer instead of merely passing the structural gates.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, is_dunder, own_scope_walk


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
    guidance = (
        "Never add a bare comparison/membership test to a counter "
        "(`count += x in seen`) — make the boolean explicit with `if <condition>: "
        "counter += 1`."
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
    guidance = (
        "Never nest a ternary inside another ternary — unfold into an if/elif "
        "statement or a dict lookup."
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
    guidance = (
        "Never write a function whose only job is manufacturing a callable — no "
        "bare `return <function name>`, `return lambda: ...`, or `return "
        "functools.partial(...)`; do the work directly or pass the plain function."
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
    guidance = (
        "Keep expression nesting (calls, arithmetic, ternaries, comprehensions, "
        "f-strings) to {max_depth} levels or fewer per statement — pull inner calls "
        "out into named intermediates."
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


_BUILTIN_NAMES = frozenset(vars(builtins))


def _is_private_helper(function: FunctionNode) -> bool:
    return (
        function.name.startswith("_")
        and not is_dunder(function.name)
        and not function.decorator_list
    )


def _sole_returned_call(function: FunctionNode) -> ast.Call | None:
    body = function.body
    if body and _is_docstring(body[0]):
        body = body[1:]
    only_returns_a_call = (
        len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.Call)
    )
    return body[0].value if only_returns_a_call else None  # type: ignore[union-attr]


def _call_root(func: ast.expr) -> ast.expr:
    """The leftmost expression a (possibly dotted) call target hangs off."""
    current = func
    while isinstance(current, ast.Attribute):
        current = current.value
    return current


def _parameter_names(function: FunctionNode) -> set[str]:
    args = function.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
    return {param.arg for param in params if param is not None}


def _delegates_elsewhere(function: FunctionNode, call: ast.Call) -> bool:
    """True when the returned call is a hop to work living somewhere else.

    A builtin callee (`return any(...)`) keeps its logic in the arguments,
    and a method on one of the function's own parameters
    (`return name.startswith("_")`) is already in front of the reader —
    neither is a hop worth chasing.
    """
    root = _call_root(call.func)
    if not isinstance(root, ast.Name):
        return True  # e.g. a constructed object's method: Renderer(...).render(...)
    if root is call.func and root.id in _BUILTIN_NAMES:
        return False
    return root.id not in _parameter_names(function)


class ThinDelegationWrapper(Rule):
    id = "SM618"
    name = "thin-delegation-wrapper"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a private function whose whole body is `return <one call to another "
        "function>` — a wrapper that only renames work and adds a hop the reviewer "
        "must chase. Public functions (API conveniences), decorated functions, "
        "dunders, builtin-wrapping one-liners (`return any(...)`), and calls on the "
        "function's own parameters are exempt."
    )
    guidance = (
        "Never write a private function whose whole body is `return <one call to "
        "another function>` — call the other function directly and delete the "
        "wrapper."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for function in ctx.functions:
            if not _is_private_helper(function):
                continue
            call = _sole_returned_call(function)
            if call is None or not _delegates_elsewhere(function, call):
                continue
            yield self.violation(
                ctx,
                function,
                ViolationDetails(
                    message=f"`{function.name}` only hands back one call to another "
                    "function — a wrapper that renames work",
                    suggestion=(
                        "name the called function for its purpose and call it "
                        "directly; delete this wrapper"
                    ),
                    symbol=function.name,
                ),
            )


def _buried_in_value_context(node: ast.BoolOp) -> bool:
    """True when the boolean expression's *value* feeds a larger expression.

    Arithmetic operands and subscript positions read as plain values, so an
    `or`-fallback there is easy to misparse. Boolean contexts (`if`/`while`
    tests, `not (...)`, a bare `return a or b`) are idiomatic and exempt.
    """
    parent = getattr(node, "parent", None)
    if isinstance(parent, (ast.BinOp, ast.Slice)):
        return True
    return isinstance(parent, ast.Subscript) and parent.slice is node


class BuriedValueFallback(Rule):
    id = "SM619"
    name = "buried-value-fallback"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags an `or`/`and` value fallback buried inside a larger expression "
        "(`(node.end_lineno or node.lineno) + 1`) — used as an arithmetic operand "
        "or subscript index, the boolean operator is easy to misread. A bare "
        "`x = a or b` and ordinary boolean conditions stay exempt."
    )
    guidance = (
        "Never bury an `or`/`and` fallback inside a larger expression as an "
        "arithmetic operand or subscript index — bind it to a named variable on "
        "its own line first."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if not isinstance(node, ast.BoolOp) or not _buried_in_value_context(node):
                continue
            snippet = ast.get_source_segment(ctx.source, node) or "<fallback>"
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message=f"value fallback `{snippet}` is buried inside a larger expression",
                    suggestion=(
                        "bind the fallback to a named variable on its own line "
                        "(e.g. `end = node.end_lineno or node.lineno`) and use the name"
                    ),
                    symbol=ctx.enclosing_symbol(node),
                ),
            )
