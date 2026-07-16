"""Binding- and annotation-level rules (SM611–SM613).

These rules reason about where names are introduced and what their static
annotations promise: a runtime ``isinstance`` check that an annotation already
guarantees, imports/locals that are never read, and bindings that shadow a
Python builtin. They share the scope-walking machinery that keeps a nested
function's bindings from being attributed to the wrong scope.
"""

from __future__ import annotations

import ast
import builtins
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import (
    IDENTIFIER,
    FunctionNode,
    Rule,
    functions,
    import_aliases,
    own_scope_walk,
)
from cleancode.rules.naming import collect_bindings


def _dotted_name(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _annotated_names(function: FunctionNode) -> dict[str, str]:
    """name -> dotted type, for simple (non-subscripted) annotations only."""
    tracked: dict[str, str] = {}
    args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    for arg in args:
        dotted = _dotted_name(arg.annotation)
        if dotted:
            tracked[arg.arg] = dotted
    for node in ast.walk(function):
        if not (isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)):
            continue
        dotted = _dotted_name(node.annotation)
        if dotted:
            tracked[node.target.id] = dotted
    return tracked


def _isinstance_call_args(node: ast.AST) -> tuple[ast.Name, ast.expr] | None:
    """``(target, type_arg)`` for an ``isinstance(target, type_arg)`` call, else ``None``."""
    if not (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
        and len(node.args) == 2
    ):
        return None
    target = node.args[0]
    if not isinstance(target, ast.Name):
        return None
    return target, node.args[1]


class RedundantIsinstanceCheck(Rule):
    id = "SM611"
    name = "redundant-isinstance-check"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `isinstance(x, T)` where `x` already carries a simple static annotation "
        "of exactly `T` — the runtime check is hallucinated safety that a type checker "
        "already guarantees, and it costs cycles in hot loops like `__getitem__`."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for function in functions(ctx.tree):
            tracked = _annotated_names(function)
            if not tracked:
                continue
            yield from self._check_function(ctx, function, tracked)

    def _check_function(
        self, ctx: FileContext, function: FunctionNode, tracked: dict[str, str]
    ) -> Iterator[Violation]:
        for node in ast.walk(function):
            match = _isinstance_call_args(node)
            if match is None:
                continue
            target, type_arg = match
            if target.id not in tracked or _dotted_name(type_arg) != tracked[target.id]:
                continue
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message=f"`isinstance({target.id}, {tracked[target.id]})` is redundant — "
                    f"`{target.id}` is already annotated `{tracked[target.id]}`",
                    suggestion="remove the check; the static annotation already "
                    "guarantees the type",
                    symbol=ctx.enclosing_symbol(node),
                ),
            )


_DYNAMIC_SCOPE_ESCAPES = frozenset({"locals", "eval", "exec"})


def _is_exempt_name(name: str) -> bool:
    return name.startswith("_")


def _dunder_all_exports(tree: ast.Module) -> set[str]:
    """String elements of a module-level ``__all__ = [...]`` assignment."""
    exports: set[str] = set()
    for node in tree.body:
        targets_all = isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        )
        if targets_all and isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            exports.update(
                element.value
                for element in node.value.elts
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            )
    return exports


def _param_annotations(function: FunctionNode) -> Iterator[ast.expr]:
    args = function.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
    return (param.annotation for param in params if param is not None and param.annotation is not None)


def _function_annotations(function: FunctionNode) -> Iterator[ast.expr]:
    yield from _param_annotations(function)
    if function.returns is not None:
        yield function.returns


def _annotation_expressions(tree: ast.Module) -> Iterator[ast.expr]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from _function_annotations(node)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            yield node.annotation


def _string_tokens(node: ast.AST) -> Iterator[str]:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield from IDENTIFIER.findall(child.value)


def _forward_ref_tokens(tree: ast.Module) -> set[str]:
    """Identifiers embedded in string-literal forward-reference annotations.

    ``from __future__ import annotations`` already defers evaluation, but some
    annotations are still spelled as an explicit string (``ctx: "FileContext"``)
    for readability. Those never appear as an ``ast.Name`` load, so an import
    used only this way needs a separate token scan to avoid a false positive.
    """
    tokens: set[str] = set()
    for annotation in _annotation_expressions(tree):
        tokens.update(_string_tokens(annotation))
    return tokens


def _referenced_names(node: ast.AST) -> set[str]:
    """Names read (or explicitly ``del``eted — a deliberate act, not dead code)."""
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Load, ast.Del))
    }


def _unpack_element_name(element: ast.expr) -> ast.Name | None:
    inner = element.value if isinstance(element, ast.Starred) else element
    return inner if isinstance(inner, ast.Name) else None


_DEFAULT_WATCHED_BUILTINS = (
    "id", "type", "list", "dict", "str", "input", "format", "filter",
    "min", "max", "sum", "hash", "object", "property", "map", "next", "iter",
)


def _class_body_field_positions(tree: ast.Module) -> set[tuple[int, int]]:
    """(lineno, col_offset) of names declared directly in a class body.

    ``id: ClassVar[str]`` and ``id = \"SM601\"`` are field names, not
    scope-shadowing locals — only a binding's *position* survives through
    ``collect_bindings``, so positions (not the AST nodes themselves) are
    what gets matched against later.
    """
    positions: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            targets = _class_body_statement_targets(statement)
            positions.update((target.lineno, target.col_offset) for target in targets)
    return positions


def _flatten_target(target: ast.expr) -> list[ast.Name] | None:
    """Name leaves of a simple (optionally tuple/list-unpacking) target, else None."""
    if isinstance(target, ast.Name):
        return [target]
    if not isinstance(target, (ast.Tuple, ast.List)):
        return None
    names = [_unpack_element_name(element) for element in target.elts]
    return names if all(name is not None for name in names) else None


def _assign_target_groups(node: ast.Assign) -> Iterator[list[ast.Name]]:
    for target in node.targets:
        names = _flatten_target(target)
        if names:
            yield names


def _assignment_groups(function: FunctionNode) -> Iterator[list[ast.Name]]:
    """Each assignment's bound-name group: one name, or every leaf of an unpack."""
    for node in own_scope_walk(function):
        if isinstance(node, ast.Assign):
            yield from _assign_target_groups(node)
        elif isinstance(node, ast.AnnAssign) and node.value is not None and isinstance(node.target, ast.Name):
            yield [node.target]
        elif isinstance(node, ast.NamedExpr) and isinstance(node.target, ast.Name):
            yield [node.target]


def _outer_scope_declared_names(function: FunctionNode) -> set[str]:
    """Names this function's own scope declares ``global``/``nonlocal``.

    Those bindings refer to state owned by an enclosing scope, so an
    assignment to one is never "dead" purely for going unread locally.
    """
    names: set[str] = set()
    for node in own_scope_walk(function):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
    return names


def _escapes_to_dynamic_scope(function: FunctionNode) -> bool:
    return any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC_SCOPE_ESCAPES
        for node in ast.walk(function)
    )


class UnusedBinding(Rule):
    id = "SM612"
    name = "unused-binding"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags an import that's never referenced anywhere in the module, and a "
        "local variable that's assigned inside a function but never read. Names "
        "already prefixed with `_`, `__all__` exports, `__init__.py` re-exports, "
        "`global`/`nonlocal` names, multi-target unpacking where at least one "
        "target is used, and functions that call `locals`/`eval`/`exec` (which "
        "can reference locals dynamically) are all exempt."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        yield from self._check_imports(ctx)
        yield from self._check_local_variables(ctx)

    def _check_imports(self, ctx: FileContext) -> Iterator[Violation]:
        if ctx.path.endswith("__init__.py"):
            return
        used = _referenced_names(ctx.tree) | _forward_ref_tokens(ctx.tree) | _dunder_all_exports(ctx.tree)
        for bound_name, alias in import_aliases(ctx.tree):
            if bound_name in used or _is_exempt_name(bound_name):
                continue
            yield self.violation(
                ctx,
                alias,
                ViolationDetails(
                    message=f"import `{bound_name}` is never used",
                    suggestion="remove the unused import",
                ),
            )

    def _check_local_variables(self, ctx: FileContext) -> Iterator[Violation]:
        for function in functions(ctx.tree):
            yield from self._check_function(ctx, function)

    def _check_function(self, ctx: FileContext, function: FunctionNode) -> Iterator[Violation]:
        if _escapes_to_dynamic_scope(function):
            return
        nonlocal_names = _outer_scope_declared_names(function)
        used = _referenced_names(function)
        for group in _assignment_groups(function):
            candidates = [
                name for name in group if not _is_exempt_name(name.id) and name.id not in nonlocal_names
            ]
            if not candidates or any(name.id in used for name in group):
                continue
            for name in candidates:
                yield self.violation(
                    ctx,
                    name,
                    ViolationDetails(
                        message=f"local variable `{name.id}` is assigned but never used",
                        suggestion=(
                            "remove the assignment, or use the value (prefix with `_` "
                            "if intentionally discarded)"
                        ),
                        symbol=function.name,
                    ),
                )


def _class_body_assign_names(target: ast.expr) -> Iterator[ast.Name]:
    """Name leaves of a class-body assignment target, including tuple/list unpacking."""
    if isinstance(target, ast.Name):
        yield target
    elif isinstance(target, (ast.Tuple, ast.List)):
        names = (_unpack_element_name(element) for element in target.elts)
        yield from (name for name in names if name is not None)


def _class_body_statement_targets(statement: ast.stmt) -> Iterator[ast.Name]:
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        yield statement.target
    elif isinstance(statement, ast.Assign):
        for target in statement.targets:
            yield from _class_body_assign_names(target)


class BuiltinShadowing(Rule):
    id = "SM613"
    name = "builtin-shadowing"
    default_severity = Severity.WARNING
    default_options: dict = {"watched": list(_DEFAULT_WATCHED_BUILTINS)}
    description = (
        "Flags a binding site (parameter, assignment target, `for`/`with ... as`/"
        "comprehension target, function/class name) whose identifier shadows a "
        "Python builtin (`id`, `type`, `list`, ...), which can cause confusing bugs "
        "if the original builtin is needed later in the same scope. A configurable "
        "`watched` list (default: the builtins most often reused as domain terms) "
        "limits noise; every entry is still checked against the live `builtins` "
        "module rather than a hardcoded copy, so it stays correct across Python "
        "versions. Class-body field declarations (`id: ClassVar[str]`, "
        "`id = \"SM601\"`) are exempt — they're field names, not shadowing locals."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        watched = set(ctx.config.options["watched"]) & vars(builtins).keys()
        exempt_positions = _class_body_field_positions(ctx.tree)
        for binding in collect_bindings(ctx.tree):
            if binding.name not in watched:
                continue
            if (binding.lineno, binding.col_offset) in exempt_positions:
                continue
            yield self.violation(
                ctx,
                binding,
                ViolationDetails(
                    message=f"{binding.kind} `{binding.name}` shadows the builtin `{binding.name}`",
                    suggestion=(
                        f"rename to avoid shadowing the builtin `{binding.name}` — "
                        "use a domain-specific name instead"
                    ),
                ),
            )
