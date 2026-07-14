"""Semantic pattern rules (SM6xx).

Plain complexity metrics (node counts, nesting depth) miss a class of smell
where the *structure* is small but the meaning is opaque: a comprehension
nested inside another, magic integer indices into an unlabeled tuple, or
control flow gated by a hardcoded string check. These rules match AST shape
rather than counting nodes.
"""

from __future__ import annotations

import ast
import re
import builtins
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, functions, subscript_base_name
from cleancode.rules.naming import collect_bindings

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
        for function in functions(ctx.tree):
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
                        suggestion="replace with `sum(iterable)`",
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
        for function in functions(ctx.tree):
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
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`len({arg}) {_op_symbol(node.ops[0])} 0` — rely on "
                        "truthiness instead",
                        suggestion=f"use `if {arg}:` or `if not {arg}:` instead of "
                        "comparing length to 0",
                        symbol=ctx.enclosing_symbol(node),
                    ),
                )


def _base_looks_like_dataset(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == "Dataset"
    if isinstance(base, ast.Attribute):
        return base.attr == "Dataset"
    return False


def _dataset_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(_base_looks_like_dataset(base) for base in node.bases):
            yield node


def _find_method(class_def: ast.ClassDef, name: str) -> FunctionNode | None:
    for item in class_def.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
            return item
    return None


def _dataset_methods(class_def: ast.ClassDef, names: tuple[str, ...]) -> Iterator[FunctionNode]:
    for name in names:
        method = _find_method(class_def, name)
        if method is not None:
            yield method


_EAGER_IO_ATTRS = frozenset({"load", "imread", "open"})


def _is_eager_io_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "open"
    if isinstance(func, ast.Attribute):
        return func.attr in _EAGER_IO_ATTRS
    return False


class EagerDatasetLoading(Rule):
    id = "SM609"
    name = "eager-dataset-loading"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags file/array loading calls (`np.load`, `open`, `Image.open`, `cv2.imread`, "
        "`torch.load`, ...) inside `__init__` of a `Dataset` subclass — eagerly loading "
        "every sample's payload at construction time defeats lazy loading and can OOM "
        "on realistic dataset sizes."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for class_def in _dataset_classes(ctx.tree):
            for method in _dataset_methods(class_def, ("__init__",)):
                yield from self._check_init(ctx, class_def, method)

    def _check_init(self, ctx: FileContext, class_def: ast.ClassDef, init: FunctionNode) -> Iterator[Violation]:
        for node in ast.walk(init):
            if isinstance(node, ast.Call) and _is_eager_io_call(node):
                snippet = ast.get_source_segment(ctx.source, node) or "<call>"
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`{snippet}` loads data eagerly inside `__init__`",
                        suggestion=(
                            "store the file path in `__init__` and load the payload lazily "
                            "in `__getitem__`"
                        ),
                        symbol=f"{class_def.name}.__init__",
                    ),
                )


def _looks_like_device_value(arg: ast.expr) -> bool:
    if isinstance(arg, ast.Constant):
        return isinstance(arg.value, str) and ("cuda" in arg.value or arg.value == "cpu")
    if isinstance(arg, ast.Call):
        return isinstance(arg.func, ast.Attribute) and arg.func.attr == "device"
    return (isinstance(arg, ast.Attribute) and "device" in arg.attr.lower()) or (
        isinstance(arg, ast.Name) and "device" in arg.id.lower()
    )


def _has_device_arg(call: ast.Call) -> bool:
    has_device_keyword = any(keyword.arg == "device" for keyword in call.keywords)
    return has_device_keyword or any(_looks_like_device_value(arg) for arg in call.args)


def _is_device_placement_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr == "cuda":
        return True
    return node.func.attr == "to" and _has_device_arg(node)


class PrematureDevicePlacement(Rule):
    id = "SM610"
    name = "premature-device-placement"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `.cuda()`/`.to(device=...)` calls inside `__init__` or `__getitem__` of a "
        "`Dataset` subclass — initializing a CUDA context before DataLoader workers fork "
        "corrupts the context across processes, causing deadlocks or segfaults."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for class_def in _dataset_classes(ctx.tree):
            for method in _dataset_methods(class_def, ("__init__", "__getitem__")):
                yield from self._check_method(ctx, class_def, method)

    def _check_method(
        self, ctx: FileContext, class_def: ast.ClassDef, method: FunctionNode
    ) -> Iterator[Violation]:
        for node in ast.walk(method):
            if isinstance(node, ast.Call) and _is_device_placement_call(node):
                snippet = ast.get_source_segment(ctx.source, node) or "<call>"
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"`{snippet}` places a tensor on-device inside `{method.name}`",
                        suggestion=(
                            "keep tensors on CPU in the Dataset; move to the target device in "
                            "the training loop after the DataLoader yields the batch"
                        ),
                        symbol=f"{class_def.name}.{method.name}",
                    ),
                )


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


_OP_SYMBOLS: dict[type, str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Lt: "<",
    ast.LtE: "<=",
}


def _op_symbol(operator: ast.cmpop) -> str:
    return _OP_SYMBOLS.get(type(operator), "?")


_SCOPE_BOUNDARY_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_DYNAMIC_SCOPE_ESCAPES = frozenset({"locals", "eval", "exec"})
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _is_exempt_name(name: str) -> bool:
    return name.startswith("_")


def _aliases_of(node: ast.stmt) -> Iterator[tuple[str, ast.alias]]:
    """Bound names introduced by one import statement, ``__future__`` excluded."""
    if isinstance(node, ast.Import):
        aliases = node.names
        return ((alias.asname or alias.name.split(".")[0], alias) for alias in aliases)
    if isinstance(node, ast.ImportFrom) and node.module != "__future__":
        aliases = node.names
        return ((alias.asname or alias.name, alias) for alias in aliases if alias.name != "*")
    return iter(())


def _import_aliases(tree: ast.Module) -> Iterator[tuple[str, ast.alias]]:
    for node in ast.walk(tree):
        yield from _aliases_of(node)


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
            yield from _IDENTIFIER.findall(child.value)


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


def _loaded_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
    }


def _own_scope_walk(function: FunctionNode) -> Iterator[ast.AST]:
    """Descendants of ``function`` in its own scope — nested def/class/lambda skipped.

    Each nested function/class is checked independently when ``functions()``
    reaches it; walking into it here would attribute its bindings to the
    wrong scope.
    """
    stack = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, _SCOPE_BOUNDARY_TYPES):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


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


def _unpack_target_name(element: ast.expr) -> ast.Name | None:
    inner = element.value if isinstance(element, ast.Starred) else element
    return inner if isinstance(inner, ast.Name) else None


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
    for node in _own_scope_walk(function):
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
    for node in _own_scope_walk(function):
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
        used = _loaded_names(ctx.tree) | _forward_ref_tokens(ctx.tree) | _dunder_all_exports(ctx.tree)
        for bound_name, alias in _import_aliases(ctx.tree):
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
        used = _loaded_names(function)
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
        names = (_unpack_target_name(element) for element in target.elts)
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
