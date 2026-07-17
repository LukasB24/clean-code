"""Names and indirection that add tokens but no information (SM620-SM622).

None of these are structural or complexity smells — the code they flag is
already short and flat. What they share is *ceremony*: a name introduced and
never used for anything but handing straight back, a second name for
something that already has one, an accessor pair that only mirrors a private
attribute. Each pattern is common in freshly generated code that names things
out of habit rather than necessity.
"""

from __future__ import annotations

import ast
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, statement_blocks


def _is_return_of(statement: ast.stmt, name: str) -> bool:
    return (
        isinstance(statement, ast.Return)
        and isinstance(statement.value, ast.Name)
        and statement.value.id == name
    )


def _is_simple_name_assign(statement: ast.stmt) -> str | None:
    """The bound name of a plain `name = expr` statement, else ``None``.

    Only a single, un-annotated ``Name`` target counts — an annotated
    assignment (`name: T = expr`) carries information beyond the expression,
    so it's exempt.
    """
    if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1):
        return None
    target = statement.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def _used_elsewhere(function: FunctionNode, name: str, skip: tuple[ast.Name, ast.Name]) -> bool:
    # skip = the pattern's own target/return nodes, not a real second use.
    for node in ast.walk(function):
        if isinstance(node, ast.Name) and node.id == name and node not in skip:
            return True
    return False


class ReturnedTemp(Rule):
    id = "SM620"
    name = "returned-temp"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `name = expr` immediately followed by `return name`, where "
        "`name` has no other use in the function — the assignment adds a name "
        "but no information. An annotated assignment (`name: T = expr`) is "
        "exempt, since the annotation itself is informative."
    )
    guidance = (
        "Never assign a value to a name only to immediately `return` that "
        "name — return the expression directly; if the name carried meaning, "
        "put it in the function name instead."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for function in ctx.functions:
            yield from self._check_function(ctx, function)

    def _check_function(self, ctx: FileContext, function: FunctionNode) -> Iterator[Violation]:
        for block in statement_blocks(function):
            yield from self._check_block(ctx, function, block)

    def _check_block(
        self, ctx: FileContext, function: FunctionNode, block: list[ast.stmt]
    ) -> Iterator[Violation]:
        for assign, follow_up in zip(block, block[1:]):
            bound = _is_simple_name_assign(assign)
            if bound is None or not _is_return_of(follow_up, bound):
                continue
            target, returned = assign.targets[0], follow_up.value
            if _used_elsewhere(function, bound, (target, returned)):
                continue
            yield self.violation(
                ctx,
                assign,
                ViolationDetails(
                    message=f"`{bound}` is assigned and immediately returned",
                    suggestion="return the expression directly; if the name "
                    "carried meaning, put it in the function name instead",
                    symbol=function.name,
                ),
            )


def _module_level_defined_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(statement.name)
    return names


def _name_to_name_assign(statement: ast.stmt) -> tuple[str, str] | None:
    if not (isinstance(statement, ast.Assign) and len(statement.targets) == 1):
        return None
    target = statement.targets[0]
    if isinstance(target, ast.Name) and isinstance(statement.value, ast.Name):
        return target.id, statement.value.id
    return None


def _is_alias_worth_flagging(statement: ast.stmt, defined: set[str]) -> tuple[str, str] | None:
    # ALL_CAPS/`_`-prefixed targets and RHS names not defined in this file
    # are deliberate, not the accidental "kept the old name too" pattern.
    pair = _name_to_name_assign(statement)
    if pair is None:
        return None
    alias, original = pair
    if alias.isupper() or alias.startswith("_") or original not in defined:
        return None
    return alias, original


class CompatibilityAlias(Rule):
    id = "SM621"
    name = "compatibility-alias"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a module-level `alias = original` where `original` is a "
        "function/class defined in the same file — a second name for "
        "something that already has one. ALL_CAPS targets, `_`-prefixed "
        "targets, and annotated assignments (`TypeAlias`) are exempt."
    )
    guidance = (
        "Never create a second module-level name for a function or class "
        "defined in the same file — call the original directly instead of "
        "aliasing it."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        defined = _module_level_defined_names(ctx.tree)
        for statement in ctx.tree.body:
            match = _is_alias_worth_flagging(statement, defined)
            if match is None:
                continue
            alias, original = match
            yield self.violation(
                ctx,
                statement,
                ViolationDetails(
                    message=f"`{alias}` is a second name for `{original}`",
                    suggestion=f"delete the alias and call `{original}` "
                    "directly — in new code nothing depends on the old name",
                ),
            )


def _self_attr_target(node: ast.expr) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _is_trivial_getter(method: FunctionNode) -> str | None:
    body = method.body
    if len(body) == 1 and isinstance(body[0], ast.Return):
        return _self_attr_target(body[0].value) if body[0].value is not None else None
    return None


def _is_trivial_setter(method: FunctionNode) -> str | None:
    # The value side must be a bare parameter (`self._x = value`), not an
    # expression — anything computed there is real setter logic, not a mirror.
    body = method.body
    if len(body) != 1 or not isinstance(body[0], ast.Assign) or len(body[0].targets) != 1:
        return None
    attr = _self_attr_target(body[0].targets[0])
    is_bare_param = isinstance(body[0].value, ast.Name)
    return attr if attr is not None and is_bare_param else None


def _decorator_names(method: FunctionNode) -> set[str]:
    names = set()
    for decorator in method.decorator_list:
        if isinstance(decorator, ast.Name):
            names.add(decorator.id)
        elif isinstance(decorator, ast.Attribute):
            names.add(decorator.attr)
    return names


class TrivialPropertyPair(Rule):
    id = "SM622"
    name = "trivial-property-pair"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags a `@property` whose body is exactly `return self._x` together "
        "with a matching `@x.setter` whose body is exactly `self._x = value` "
        "— both trivial, mirroring a private attribute with no logic in "
        "between. A getter-only read-only property (no matching setter) is a "
        "legitimate idiom and is exempt; any validation or computation in "
        "either accessor exempts the pair."
    )
    guidance = (
        "Never write a `@property`/`@x.setter` pair that only mirrors "
        "`self._x` — use a plain public attribute `x` instead; introduce a "
        "property later only when logic is actually needed."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for node in ast.walk(ctx.tree):
            if isinstance(node, ast.ClassDef):
                yield from self._check_class(ctx, node)

    def _check_class(self, ctx: FileContext, class_def: ast.ClassDef) -> Iterator[Violation]:
        getters = self._trivial_getters(class_def)
        setters = self._trivial_setter_names(class_def)
        for name, getter in getters.items():
            if name not in setters:
                continue
            yield self.violation(
                ctx,
                getter,
                ViolationDetails(
                    message=f"property `{name}` and its setter only mirror `self._{name}`",
                    suggestion=f"use a plain attribute `{name}`; introduce a "
                    "property later only when logic is needed",
                    symbol=class_def.name,
                ),
            )

    @staticmethod
    def _trivial_getters(class_def: ast.ClassDef) -> dict[str, FunctionNode]:
        getters: dict[str, FunctionNode] = {}
        for item in class_def.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if "property" not in _decorator_names(item):
                continue
            if _is_trivial_getter(item) == f"_{item.name}":
                getters[item.name] = item
        return getters

    @staticmethod
    def _trivial_setter_names(class_def: ast.ClassDef) -> set[str]:
        names: set[str] = set()
        for item in class_def.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if f"{item.name}.setter" not in _decorator_sources(item):
                continue
            if _is_trivial_setter(item) == f"_{item.name}":
                names.add(item.name)
        return names


def _decorator_sources(method: FunctionNode) -> set[str]:
    """Every decorator rendered as dotted text, so `@x.setter` becomes `"x.setter"`."""
    sources = set()
    for decorator in method.decorator_list:
        if isinstance(decorator, ast.Attribute) and isinstance(decorator.value, ast.Name):
            sources.add(f"{decorator.value.id}.{decorator.attr}")
    return sources
