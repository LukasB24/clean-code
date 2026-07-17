"""Semantic pattern rules (SM6xx).

Plain complexity metrics (node counts, nesting depth) miss a class of smell
where the *structure* is small but the meaning is opaque: a comprehension
nested inside another, magic integer indices into an unlabeled tuple, or
control flow gated by a hardcoded string check. These rules match AST shape
rather than counting nodes.
"""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, subscript_base_name

_COMP_TYPES = (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)


def _nested_ternary_comprehension(node: ast.AST) -> ast.AST | None:
    """A comprehension nested inside ``node`` whose filter is itself a ternary."""
    for child in ast.walk(node):
        if child is node:
            continue
        if isinstance(child, _COMP_TYPES) and any(
            isinstance(test, ast.IfExp) for comp in child.generators for test in comp.ifs
        ):
            return child
    return None


class ComprehensionDensity(Rule):
    id = "SM601"
    name = "comprehension-density"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a comprehension that nests another comprehension whose filter "
        "condition is itself an inline ternary — logical over-compression that's "
        "nearly impossible to read at a glance."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if isinstance(node, _COMP_TYPES) and _nested_ternary_comprehension(node) is not None:
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message="comprehension nests another comprehension filtered by a ternary",
                        suggestion=(
                            "pull the nested comprehension and its ternary condition "
                            "into a named helper function"
                        ),
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


def _is_fixed_tuple(annotation: ast.expr) -> bool:
    """True for ``tuple[T1, T2, ...]`` with 2+ concrete elements.

    Excludes the variadic ``tuple[T, ...]`` form: that's a homogeneous
    sequence, not a positional struct, so indexing it isn't anonymous.
    """
    if not (isinstance(annotation, ast.Subscript) and subscript_base_name(annotation) == "tuple"):
        return False
    slice_ = annotation.slice
    elements = list(slice_.elts) if isinstance(slice_, ast.Tuple) else [slice_]
    if len(elements) < 2:
        return False
    return not any(
        isinstance(element, ast.Constant) and element.value is Ellipsis for element in elements
    )


def _tuple_annotated_params(function: FunctionNode) -> set[str]:
    args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    return {arg.arg for arg in args if arg.annotation is not None and _is_fixed_tuple(arg.annotation)}


def _is_int_index_of(node: ast.Subscript, tracked: set[str]) -> bool:
    return (
        isinstance(node.value, ast.Name)
        and node.value.id in tracked
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, int)
        and not isinstance(node.slice.value, bool)
    )


class AnonymousTupleIndexing(Rule):
    id = "SM602"
    name = "anonymous-tuple-indexing"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags integer-constant indexing (`bounds[0]`) into a parameter annotated as "
        "a fixed multi-element tuple — primitive obsession that hides what each "
        "position means. Variadic `tuple[T, ...]` parameters are exempt."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for function in ctx.functions:
            tracked = _tuple_annotated_params(function)
            if not tracked:
                continue
            yield from self._check_function(ctx, function, tracked)

    def _check_function(
        self, ctx: FileContext, function: FunctionNode, tracked: set[str]
    ) -> Iterator[Violation]:
        for node in ast.walk(function):
            if isinstance(node, ast.Subscript) and _is_int_index_of(node, tracked):
                name = node.value.id  # type: ignore[union-attr]
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`{name}[{node.slice.value}]` indexes tuple parameter "  # type: ignore[union-attr]
                        f"`{name}` by position — meaning is opaque",
                        suggestion=(
                            "replace the tuple parameter with a NamedTuple/dataclass with "
                            "named fields, or unpack it once at the top of the function"
                        ),
                        symbol=function.name,
                    ),
                )


_STRING_TEST_METHODS = frozenset({"startswith", "endswith", "find", "rfind"})


def _is_magic_string_test(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Attribute)
        and test.func.attr in _STRING_TEST_METHODS
        and bool(test.args)
        and isinstance(test.args[0], ast.Constant)
        and isinstance(test.args[0].value, str)
    )


class MagicStringBranching(Rule):
    id = "SM603"
    name = "magic-string-branching"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags inline ternaries (`a if x.startswith('...') else b`) whose branch is "
        "chosen by a hardcoded string prefix/suffix/substring check — the domain "
        "rule hides inside a string literal instead of a named condition."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if isinstance(node, ast.IfExp) and _is_magic_string_test(node.test):
                snippet = ast.get_source_segment(ctx.source, node.test) or "<call>"
                yield self.violation(
                    ctx,
                    node.test,
                    ViolationDetails(
                        message=f"ternary branches on a hardcoded string check: `{snippet}`",
                        suggestion=(
                            "name the condition (e.g. `is_transaction_metric = "
                            "k.startswith('tx_')`) so the branch reflects a domain "
                            "concept, not a string literal"
                        ),
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


def _bool_constant(node: ast.expr) -> bool | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return None


class RedundantBooleanTernary(Rule):
    id = "SM604"
    name = "redundant-boolean-ternary"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags ternaries that return explicit `True`/`False` literals for a condition "
        "that already evaluates to a boolean (`True if x == y else False`) — the "
        "ternary itself is the redundant part."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if not isinstance(node, ast.IfExp):
                continue
            body_value = _bool_constant(node.body)
            orelse_value = _bool_constant(node.orelse)
            if body_value is None or orelse_value is None or body_value == orelse_value:
                continue
            condition = ast.get_source_segment(ctx.source, node.test) or "<condition>"
            suggestion = condition if body_value else f"not ({condition})"
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message="ternary returns explicit True/False for an already-boolean condition",
                    suggestion=f"replace the ternary with `{suggestion}`",
                    symbol=ctx.enclosing_symbol(node),
                ),
            )


_ADD_LAMBDA_PARAMS = 2


def _is_add_lambda(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Lambda)
        and len(node.args.args) == _ADD_LAMBDA_PARAMS
        and isinstance(node.body, ast.BinOp)
        and isinstance(node.body.op, ast.Add)
    )


def _reduce_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class ReduceInsteadOfSum(Rule):
    id = "SM605"
    name = "reduce-instead-of-sum"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `functools.reduce(lambda a, b: a + b, xs)` — a built-in `sum(xs)` "
        "does the same thing, faster and without the lambda indirection."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if (
                isinstance(node, ast.Call)
                and _reduce_name(node.func) == "reduce"
                and node.args
                and _is_add_lambda(node.args[0])
            ):
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message="`reduce(lambda a, b: a + b, ...)` reimplements the "
                        "built-in `sum()`",
                        suggestion="replace with `sum(iterable)` for numbers, or "
                        "`''.join(parts)` when concatenating strings",
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


def _comprehension_iters(function: FunctionNode) -> Iterator[ast.expr]:
    for node in ast.walk(function):
        if isinstance(node, _COMP_TYPES):
            yield from (generator.iter for generator in node.generators)


def _iterated_source_signatures(function: FunctionNode, source: str) -> Iterator[tuple[str, ast.expr]]:
    """(signature, iter node) for each comprehension's iterated collection.

    Only non-`Name` iter expressions (`item["metrics"]`, `ctx.comments`,
    `get_rows()`) are yielded — a bare local variable being consumed by a
    second comprehension is normally an ordinary filter-then-map step, not a
    second pass over a shared data source.
    """
    for iter_node in _comprehension_iters(function):
        if not isinstance(iter_node, ast.Name):
            signature = ast.get_source_segment(source, iter_node) or ast.dump(iter_node)
            yield signature, iter_node


class RepeatedCollectionIteration(Rule):
    id = "SM606"
    name = "repeated-collection-iteration"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a comprehension that iterates over a collection expression "
        "(`item[\"metrics\"]`, `self.rows`, `get_data()`) already iterated by an "
        "earlier comprehension in the same function — two passes where one would do."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for function in ctx.functions:
            yield from self._check_function(ctx, function)

    def _check_function(self, ctx: FileContext, function: FunctionNode) -> Iterator[Violation]:
        first_seen: dict[str, ast.expr] = {}
        for signature, iter_node in _iterated_source_signatures(function, ctx.source):
            first = first_seen.get(signature)
            if first is None:
                first_seen[signature] = iter_node
                continue
            yield self.violation(
                ctx,
                iter_node,
                ViolationDetails(
                    message=f"`{signature}` is iterated again here — already iterated "
                    f"at line {first.lineno}",
                    suggestion="merge into a single pass: derive both results from one "
                    "comprehension/loop",
                    symbol=function.name,
                ),
            )


_DEFAULT_MAGIC_NUMBER_IGNORE = (0, 1, -1, 2, 10)


def _numeric_value(node: ast.expr) -> int | float | None:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _numeric_value(node.operand)
        return -value if value is not None else None
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    return None


def _numeric_operand_sites(tree: ast.Module) -> Iterator[tuple[ast.expr, ast.expr]]:
    """(parent node, operand) for every direct BinOp/Compare operand in the tree."""
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp):
            yield from ((node, operand) for operand in (node.left, node.right))
        elif isinstance(node, ast.Compare):
            yield from ((node, operand) for operand in (node.left, *node.comparators))


class MagicNumber(Rule):
    id = "SM607"
    name = "magic-number"
    default_severity = Severity.WARNING
    default_options: dict = {"ignore": list(_DEFAULT_MAGIC_NUMBER_IGNORE)}
    description = (
        "Flags numeric literals embedded directly in a binary operation or comparison "
        "(`threshold * 1.2`) instead of a named, typed constant. A configurable "
        "`ignore` list (default 0, 1, -1, 2, 10) exempts domain-agnostic values."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        ignore = set(ctx.config.options["ignore"])
        for node, operand in _numeric_operand_sites(ctx.tree):
            value = _numeric_value(operand)
            if value is not None and value not in ignore:
                yield self.violation(
                    ctx,
                    operand,
                    ViolationDetails(
                        message=f"magic number `{value}` — extract it to a named, typed constant",
                        suggestion=f"e.g. `SOME_DESCRIPTIVE_NAME = {value}`",
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


def _is_len_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len" and len(node.args) == 1


def _is_zero(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0 and not isinstance(node.value, bool)


class NonIdiomaticEmptinessCheck(Rule):
    id = "SM608"
    name = "non-idiomatic-emptiness-check"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `len(x) > 0` / `len(x) == 0` style checks — Python sequences are "
        "already truthy/falsy, so PEP 8 prefers `if x:` / `if not x:`."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if (
                isinstance(node, ast.Compare)
                and _is_len_call(node.left)
                and len(node.comparators) == 1
                and _is_zero(node.comparators[0])
            ):
                arg = ast.get_source_segment(ctx.source, node.left.args[0]) or "x"  # type: ignore[attr-defined]
                operator = _OP_SYMBOLS.get(type(node.ops[0]), "?")
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`len({arg}) {operator} 0` — rely on "
                        "truthiness instead",
                        suggestion=f"use `if {arg}:` or `if not {arg}:` instead of "
                        "comparing length to 0",
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


_OP_SYMBOLS: dict[type, str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Lt: "<",
    ast.LtE: "<=",
}
