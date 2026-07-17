"""SOLID-adjacent rules (SD8xx).

Both rules here stay within one file's AST — no project-wide type resolution —
so they're plain per-file ``Rule``s, not ``ProjectRule``s. LSP/ISP/DIP checks
are deliberately out of scope: reliably detecting them needs cross-file type
and interface resolution that risks false positives this project guards
against with its dirty/clean fixture tests.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, Rule, is_dunder, is_elif_branch


def _is_isinstance_call(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "isinstance"
        and len(test.args) == 2
    )


def _is_type_is_compare(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], (ast.Is, ast.Eq))
        and isinstance(test.left, ast.Call)
        and isinstance(test.left.func, ast.Name)
        and test.left.func.id == "type"
        and len(test.left.args) == 1
    )


def _references_ast_module(node: ast.expr) -> bool:
    """True for ``ast.If`` / ``(ast.If, ast.For)`` — Python's own, closed node hierarchy.

    Switching on *this* type set is a routine, idiomatic part of AST tooling
    (the alternative is ``ast.NodeVisitor``, not polymorphism over new
    subclasses this codebase would ever add) — a fundamentally different
    situation from switching on an extensible, project-defined type, so it's
    exempt from the OCP check below.
    """
    if isinstance(node, ast.Attribute):
        return isinstance(node.value, ast.Name) and node.value.id == "ast"
    if isinstance(node, ast.Tuple):
        return bool(node.elts) and all(_references_ast_module(elt) for elt in node.elts)
    return False


def _type_check_target(test: ast.expr) -> str | None:
    """The variable name a branch type-switches on, or ``None`` if it isn't one."""
    if _is_isinstance_call(test):
        type_arg = test.args[1]  # type: ignore[union-attr]
        if _references_ast_module(type_arg):
            return None
        target = test.args[0]  # type: ignore[union-attr]
        return target.id if isinstance(target, ast.Name) else None
    if _is_type_is_compare(test):
        if _references_ast_module(test.comparators[0]):
            return None
        arg = test.left.args[0]  # type: ignore[union-attr]
        return arg.id if isinstance(arg, ast.Name) else None
    return None


def _elif_chain(node: ast.If) -> Iterator[ast.If]:
    """``node`` followed by each subsequent true ``elif`` branch in its chain.

    Stops at a hand-written ``else:\\n    if ...`` (a nested if, not an
    elif) rather than folding it into the same type-switch chain.
    """
    current: ast.If | None = node
    while current is not None:
        yield current
        if len(current.orelse) == 1 and is_elif_branch(current.orelse[0]):
            current = current.orelse[0]
        else:
            current = None


def _common_type_switch(branches: list[ast.If], min_branches: int) -> tuple[str, int] | None:
    """The (name, count) of a leading run of branches type-switching on one name."""
    targets = [_type_check_target(branch.test) for branch in branches]
    if not targets or targets[0] is None:
        return None
    name = targets[0]
    count = 0
    for target in targets:
        if target != name:
            break
        count += 1
    return (name, count) if count >= min_branches else None


class TypeSwitchViolatesOCP(Rule):
    id = "SD801"
    name = "type-switch-violates-ocp"
    default_severity = Severity.WARNING
    default_options = {"min_branches": 3}
    description = (
        "Flags an if/elif chain of `min_branches`-or-more (default 3) branches that "
        "each test `isinstance(x, ...)`/`type(x) is ...` against the same variable — "
        "adding a new type means editing this chain instead of extending via "
        "polymorphism, the classic Open/Closed Principle violation."
    )
    guidance = (
        "Never chain {min_branches}-or-more `isinstance`/`type()` branches on the "
        "same variable — use polymorphism (a method per type) or a "
        "`dict[type, Callable]` dispatch table."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        min_branches = ctx.config.options["min_branches"]
        for node in ast.walk(ctx.tree):
            if not isinstance(node, ast.If) or is_elif_branch(node):
                continue
            match = _common_type_switch(list(_elif_chain(node)), min_branches)
            if match is None:
                continue
            name, count = match
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message=f"{count} branches switch on the type of `{name}` — a "
                    "type-switch violates the Open/Closed Principle",
                    suggestion=(
                        "replace with polymorphism (a method per type) or a "
                        "`dict[type, Callable]` dispatch table"
                    ),
                    symbol=ctx.enclosing_symbol(node),
                ),
            )


def _is_non_instance_method(method: FunctionNode) -> bool:
    return any(
        isinstance(decorator, ast.Name) and decorator.id in ("staticmethod", "classmethod")
        for decorator in method.decorator_list
    )


def _instance_methods(class_def: ast.ClassDef) -> list[FunctionNode]:
    """Non-dunder, non-static/classmethod methods — the ones cohesion applies to."""
    return [
        item
        for item in class_def.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not is_dunder(item.name)
        and not _is_non_instance_method(item)
    ]


def _self_param_name(method: FunctionNode) -> str | None:
    params = [*method.args.posonlyargs, *method.args.args]
    return params[0].arg if params else None


def _is_self_attribute(node: ast.AST, self_name: str) -> bool:
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == self_name


def _self_data_attrs(method: FunctionNode, self_name: str) -> set[str]:
    """Instance attributes ``method`` reads/writes directly (not through a method call)."""
    attrs = set()
    for node in ast.walk(method):
        if not _is_self_attribute(node, self_name):
            continue
        parent = getattr(node, "parent", None)
        if isinstance(parent, ast.Call) and parent.func is node:
            continue  # a self.method(...) call; tracked separately as a call edge
        attrs.add(node.attr)
    return attrs


def _self_called_methods(method: FunctionNode, self_name: str, sibling_names: set[str]) -> set[str]:
    """A delegation edge counts the same as a shared attribute for cohesion purposes."""
    return {
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and _is_self_attribute(node.func, self_name)
        and node.func.attr in sibling_names  # type: ignore[union-attr]
    }


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent = {item: item for item in items}
        self.attr_owner: dict[str, str] = {}

    def find(self, item: str) -> str:
        while self.parent[item] != item:
            item = self.parent[item]
        return item

    def union(self, first: str, second: str) -> None:
        root_first, root_second = self.find(first), self.find(second)
        if root_first != root_second:
            self.parent[root_first] = root_second

    def link_via_attr(self, method: str, attr: str) -> None:
        """Union ``method`` with whichever earlier method first touched ``attr``."""
        owner = self.attr_owner.get(attr)
        if owner is None:
            self.attr_owner[attr] = method
        else:
            self.union(method, owner)


def _method_groups(methods: list[FunctionNode]) -> list[list[str]]:
    """Connected components of method names, linked by shared attributes or calls.

    Nodes sharing a name — a ``@property``/``@x.setter``/``@x.deleter`` trio, or
    ``@overload`` stubs — are folded into one logical method first, so a getter/
    setter pair isn't miscounted as two unrelated methods with nothing in common.
    """
    names = sorted({method.name for method in methods})
    union_find = _UnionFind(names)
    for method in methods:
        self_name = _self_param_name(method)
        if self_name is None:
            continue
        for attr in _self_data_attrs(method, self_name):
            union_find.link_via_attr(method.name, attr)
        sibling_names = set(names) - {method.name}
        for called_name in _self_called_methods(method, self_name, sibling_names):
            union_find.union(method.name, called_name)

    groups: dict[str, list[str]] = defaultdict(list)
    for name in names:
        groups[union_find.find(name)].append(name)
    return list(groups.values())


@dataclass(frozen=True)
class _CohesionOptions:
    min_methods: int
    exempt_name_suffixes: tuple[str, ...]


class LowCohesionClass(Rule):
    id = "SD802"
    name = "low-cohesion-class"
    default_severity = Severity.WARNING
    default_options = {"min_methods": 4, "exempt_name_suffixes": ["Mixin"]}
    description = (
        "Flags a class whose instance methods split into two or more *multi-member* "
        "groups that share no instance attribute and never call each other — a "
        "concrete proxy for 'this class does more than one thing' (SRP), beyond the "
        "line-count check in ST103. A single method with no shared state (a stray "
        "pure helper) does not count as its own group — only genuine clusters of "
        "mutually-related methods do. Dunder methods and @staticmethod/@classmethod "
        "helpers are always excluded; classes whose name ends with one of "
        "`exempt_name_suffixes` (default `Mixin`, since mixins are intentionally "
        "composed from independent, reusable behavior) are exempt entirely."
    )
    guidance = (
        "Give a class's methods one shared purpose — if it splits into unrelated "
        "clusters sharing no state or calls, split it into separate classes."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        options = _CohesionOptions(
            min_methods=ctx.config.options["min_methods"],
            exempt_name_suffixes=tuple(ctx.config.options["exempt_name_suffixes"]),
        )
        for node in ast.walk(ctx.tree):
            if isinstance(node, ast.ClassDef):
                yield from self._check_class(ctx, node, options)

    def _check_class(
        self, ctx: FileContext, class_def: ast.ClassDef, options: _CohesionOptions
    ) -> Iterable[Violation]:
        clusters = self._eligible_clusters(class_def, options)
        if clusters is None:
            return
        pretty = "; ".join(", ".join(sorted(cluster)) for cluster in clusters)
        yield self.violation(
            ctx,
            class_def,
            ViolationDetails(
                message=f"class `{class_def.name}` splits into {len(clusters)} unrelated "
                f"method clusters sharing no instance attribute or call: {pretty}",
                suggestion="split the class along its disjoint method clusters",
                symbol=class_def.name,
            ),
        )

    @staticmethod
    def _eligible_clusters(
        class_def: ast.ClassDef, options: _CohesionOptions
    ) -> list[list[str]] | None:
        """The class's disjoint method clusters, or ``None`` if it shouldn't be flagged."""
        if class_def.name.endswith(options.exempt_name_suffixes):
            return None
        methods = _instance_methods(class_def)
        if len({method.name for method in methods}) < options.min_methods:
            return None
        clusters = [group for group in _method_groups(methods) if len(group) >= 2]
        return clusters if len(clusters) >= 2 else None
