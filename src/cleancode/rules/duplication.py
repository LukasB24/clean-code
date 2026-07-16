"""Cross-file duplication rule (DP7xx).

Unlike the per-file rules, this one is a ``ProjectRule``: it sees every parsed
file in one analysis run at once, which is the only way to catch a function
copy-pasted into another module (or another class in the same file).
"""

from __future__ import annotations

import ast
import copy
from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Callable, ClassVar, Iterable

from cleancode.models import Location, ParsedFile, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, ProjectRule, functions, import_aliases, is_dunder

if TYPE_CHECKING:
    from cleancode.config import Config


class _Anonymizer(ast.NodeTransformer):
    """Blanks variable/parameter/attribute names in a (copied) AST in place.

    Call targets are preserved: two bodies that call different functions
    (``json.dumps(x)`` vs ``pickle.loads(x)``) are doing different things,
    not copy-pasting each other. A call's receiver chain is preserved too
    when it is rooted at an imported name — ``json.dumps`` and ``yaml.dumps``
    name different APIs — while a variable receiver stays blanked, because
    ``fh.write`` vs ``out.write`` is just a rename.
    """

    def __init__(self, imported_names: set[str]) -> None:
        self._imported_names = imported_names
        self._call_targets: set[ast.AST] = set()

    def visit_Call(self, node: ast.Call) -> ast.AST:
        if isinstance(node.func, (ast.Name, ast.Attribute)):
            self._call_targets.add(node.func)
            self._preserve_imported_receiver(node.func)
        self.generic_visit(node)
        return node

    def _preserve_imported_receiver(self, func: ast.expr) -> None:
        chain: list[ast.AST] = []
        current = func.value if isinstance(func, ast.Attribute) else None
        while isinstance(current, ast.Attribute):
            chain.append(current)
            current = current.value
        if isinstance(current, ast.Name) and current.id in self._imported_names:
            self._call_targets.add(current)
            self._call_targets.update(chain)

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if node not in self._call_targets:
            node.id = "_"
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        if node not in self._call_targets:
            node.attr = "_"
        self.generic_visit(node)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST:
        node.arg = "_"
        self.generic_visit(node)
        return node

    def visit_keyword(self, node: ast.keyword) -> ast.AST:
        if node.arg is not None:
            node.arg = "_"
        self.generic_visit(node)
        return node


def _normalized_dump(node: ast.AST, imported_names: set[str]) -> str:
    """``ast.dump`` with variable/parameter/attribute names blanked out.

    Two statements with identical control flow and literals but different
    names (``rows`` vs ``items``) dump to the same string; called function/
    method names (with any imported-module receiver), and literal constants
    still tell them apart, so this stays conservative.
    """
    anonymized = _Anonymizer(imported_names).visit(copy.deepcopy(node))
    return ast.dump(anonymized, annotate_fields=True, include_attributes=False)


def _is_docstring_expr(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _significant_body(function: FunctionNode) -> list[ast.stmt]:
    """The function body with a leading docstring (if any) stripped."""
    body = function.body
    if body and _is_docstring_expr(body[0]):
        return body[1:]
    return body


def _raises_not_implemented(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Raise):
        return False
    exc = statement.exc
    if isinstance(exc, ast.Call):
        exc = exc.func
    return isinstance(exc, ast.Name) and exc.id == "NotImplementedError"


def _is_stub_body(body: list[ast.stmt]) -> bool:
    """True for a body that's just a placeholder, not real logic to compare."""
    if len(body) != 1:
        return False
    statement = body[0]
    is_ellipsis = (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
    )
    return isinstance(statement, ast.Pass) or is_ellipsis or _raises_not_implemented(statement)


def _exact_dump(node: ast.AST) -> str:
    """``ast.dump`` as written: identifiers are kept, so only true copies collide."""
    return ast.dump(node, annotate_fields=True, include_attributes=False)


_Member = tuple[ParsedFile, FunctionNode]
_Fingerprint = Callable[[ast.AST], str]
# Builds one file's fingerprint function, so a fingerprint can depend on
# file-level facts (which names are imports) computed once per file.
_FingerprintFactory = Callable[[ParsedFile], _Fingerprint]


def _normalized_fingerprint(parsed: ParsedFile) -> _Fingerprint:
    imported = {name for name, _ in import_aliases(parsed.tree)}
    return partial(_normalized_dump, imported_names=imported)


def _exact_fingerprint(_parsed: ParsedFile) -> _Fingerprint:
    return _exact_dump


def _body_fingerprint(
    function: FunctionNode, min_statements: int, fingerprint: _Fingerprint
) -> str | None:
    """Comparable fingerprint of a function's body, or ``None`` if exempt.

    Dunder methods, stub bodies, and bodies shorter than ``min_statements``
    are never compared; a leading docstring is stripped first.
    """
    if is_dunder(function.name):
        return None
    body = _significant_body(function)
    if len(body) < min_statements or _is_stub_body(body):
        return None
    return "|".join(fingerprint(statement) for statement in body)


def _comparable_members(
    files: list[ParsedFile], min_statements: int, make_fingerprint: _FingerprintFactory
) -> Iterable[tuple[str, _Member]]:
    for parsed in files:
        yield from _file_members(parsed, min_statements, make_fingerprint(parsed))


def _file_members(
    parsed: ParsedFile, min_statements: int, fingerprint: _Fingerprint
) -> Iterable[tuple[str, _Member]]:
    for function in functions(parsed.tree):
        key = _body_fingerprint(function, min_statements, fingerprint)
        if key is not None:
            yield key, (parsed, function)


def _grouped_by_fingerprint(
    files: list[ParsedFile], min_statements: int, make_fingerprint: _FingerprintFactory
) -> Iterable[list[_Member]]:
    """Groups of two-or-more functions whose fingerprinted bodies collide."""
    groups: dict[str, list[_Member]] = defaultdict(list)
    for key, member in _comparable_members(files, min_statements, make_fingerprint):
        groups[key].append(member)
    return [members for members in groups.values() if len(members) >= 2]


@dataclass(frozen=True)
class _DuplicateWording:
    """How one duplication rule phrases its violations."""

    verb: str
    suggestion: str


class _DuplicationRule(ProjectRule):
    """Shared reporting for rules that group functions by a body fingerprint."""

    _WORDING: ClassVar[_DuplicateWording]

    def _flag_group(self, config: "Config", members: list[_Member]) -> Iterable[Violation]:
        """One violation per member after the first, pointing back at the original."""
        first_parsed, first_function = members[0]
        for parsed, function in members[1:]:
            yield self.violation(
                config,
                Location(path=parsed.path, node=function),
                ViolationDetails(
                    message=f"function `{function.name}` {self._WORDING.verb} "
                    f"`{first_function.name}` at {first_parsed.path}:{first_function.lineno}",
                    suggestion=self._WORDING.suggestion,
                    symbol=function.name,
                ),
            )


class DuplicateFunctionBody(_DuplicationRule):
    id = "DP701"
    name = "duplicate-function-body"
    default_severity = Severity.WARNING
    default_options = {"min_statements": 4}
    description = (
        "Flags two or more functions/methods, anywhere in the analyzed files, whose "
        "bodies are structurally identical once names are ignored — copy-paste DRY "
        "violations a single-file rule can't see. Stub bodies (pass/.../raise "
        "NotImplementedError), dunder methods, and bodies shorter than `min_statements` "
        "are exempt."
    )

    _WORDING = _DuplicateWording(
        verb="duplicates the body of",
        suggestion="extract the shared logic into a common helper function",
    )

    def check_project(self, files: list[ParsedFile], config: "Config") -> Iterable[Violation]:
        min_statements = config.rules[self.id].options["min_statements"]
        for members in _grouped_by_fingerprint(files, min_statements, _normalized_fingerprint):
            yield from self._flag_group(config, members)


class IdenticalFunctionImplementation(_DuplicationRule):
    id = "DP702"
    name = "identical-function-implementation"
    default_severity = Severity.WARNING
    default_options = {"min_statements": 2}
    description = (
        "Flags two or more functions/methods whose bodies are exactly identical, "
        "identifiers included — the same implementation pasted twice, like a private "
        "helper that drifted into a second module. Requiring identifiers to match is "
        "what lets this rule inspect much shorter bodies (default 2 statements) than "
        "DP701 without noise; bodies long enough for DP701 to report are left to "
        "DP701. Stub bodies and dunder methods are exempt."
    )

    _WORDING = _DuplicateWording(
        verb="is an exact copy of",
        suggestion="keep one copy and import/reuse it from the other location",
    )

    def check_project(self, files: list[ParsedFile], config: "Config") -> Iterable[Violation]:
        min_statements = config.rules[self.id].options["min_statements"]
        dp701 = config.rules[DuplicateFunctionBody.id]
        for members in _grouped_by_fingerprint(files, min_statements, _exact_fingerprint):
            if dp701.enabled and self._covered_by_dp701(members, dp701.options["min_statements"]):
                continue  # DP701 already reports this group; don't double-flag
            yield from self._flag_group(config, members)

    @staticmethod
    def _covered_by_dp701(members: list[_Member], dp701_min_statements: int) -> bool:
        _, first_function = members[0]
        return len(_significant_body(first_function)) >= dp701_min_statements
