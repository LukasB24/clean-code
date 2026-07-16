"""Type-hint rules: reject uninformative annotations (TY5xx)."""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, subscript_base_name


def _annotations(function: FunctionNode) -> Iterator[tuple[ast.expr, str]]:
    """Yield (annotation, label) for each annotated parameter and the return type."""
    args = function.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
    for arg in params:
        if arg is not None and arg.annotation is not None:
            yield arg.annotation, f"parameter `{arg.arg}`"
    if function.returns is not None:
        yield function.returns, "return type"


def _is_any(node: ast.expr) -> bool:
    """True for a bare ``Any`` reference, written plain or as ``typing.Any``."""
    return (isinstance(node, ast.Name) and node.id == "Any") or (
        isinstance(node, ast.Attribute) and node.attr == "Any"
    )


def _slice_elements(node: ast.Subscript) -> list[ast.expr]:
    inner = node.slice
    return list(inner.elts) if isinstance(inner, ast.Tuple) else [inner]


def _reduces_to_any(annotation: ast.expr) -> bool:
    """True when the whole annotation is semantically ``Any``.

    Bare ``Any``, ``Optional[Any]``, ``Any | None``, and ``Union[Any, ...]`` all
    qualify, because each is just ``Any`` wearing a hat. ``Any`` nested as a type
    argument (``dict[str, Any]``, ``list[Any]``) does not — a structured container
    carrying an ``Any`` payload is the justified exception.
    """
    if _is_any(annotation):
        return True
    if isinstance(annotation, ast.Subscript):
        if subscript_base_name(annotation) in ("Optional", "Union"):
            return any(_reduces_to_any(elt) for elt in _slice_elements(annotation))
        return False
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _reduces_to_any(annotation.left) or _reduces_to_any(annotation.right)
    return False


class UninformativeAny(Rule):
    id = "TY501"
    name = "uninformative-any"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Rejects annotations that reduce to bare `Any` (including `Optional[Any]` "
        "and `Any | None`) on parameters and return types. `Any` nested in a "
        "container such as `dict[str, Any]` is permitted as a justified exception."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for function in ctx.functions:
            yield from self._check_function(ctx, function)

    def _check_function(
        self, ctx: FileContext, function: FunctionNode
    ) -> Iterator[Violation]:
        for annotation, label in _annotations(function):
            if _reduces_to_any(annotation):
                yield self.violation(
                    ctx,
                    annotation,
                    ViolationDetails(
                        message=f"{label} of `{function.name}` is annotated with bare `Any`",
                        suggestion=(
                            "use a structured type (`TypedDict`, a dataclass) or `object` "
                            "for a truly arbitrary value; reserve `Any` for container "
                            "payloads like `dict[str, Any]`"
                        ),
                        symbol=function.name,
                    ),
                )
