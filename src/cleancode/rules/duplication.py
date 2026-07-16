"""Cross-file duplication rule (DP7xx).

Unlike the per-file rules, this one is a ``ProjectRule``: it sees every parsed
file in one analysis run at once, which is the only way to catch a function
copy-pasted into another module (or another class in the same file).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, ClassVar, Iterable

from cleancode.models import Location, ParsedFile, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, ProjectRule, import_aliases, is_dunder

if TYPE_CHECKING:
    from cleancode.config import Config


def _preserved_nodes(statement: ast.AST, imported_names: set[str]) -> set[ast.AST]:
    """The nodes whose identifiers survive anonymization: call targets.

    Two bodies that call different functions (``json.dumps(x)`` vs
    ``pickle.loads(x)``) are doing different things, not copy-pasting each
    other. A call's receiver chain survives too when it is rooted at an
    imported name — ``json.dumps`` and ``yaml.dumps`` name different APIs —
    while a variable receiver stays anonymized, because ``fh.write`` vs
    ``out.write`` is just a rename.
    """
    preserved: set[ast.AST] = set()
    for node in ast.walk(statement):
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute)):
            preserved.add(node.func)
            _extend_with_imported_receiver(preserved, node.func, imported_names)
    return preserved


def _extend_with_imported_receiver(
    preserved: set[ast.AST], func: ast.expr, imported_names: set[str]
) -> None:
    chain: list[ast.AST] = []
    current = func.value if isinstance(func, ast.Attribute) else None
    while isinstance(current, ast.Attribute):
        chain.append(current)
        current = current.value
    if isinstance(current, ast.Name) and current.id in imported_names:
        preserved.add(current)
        preserved.update(chain)


# Identifier-carrying fields that anonymization blanks (unless preserved).
_IDENTIFIER_FIELDS = {(ast.Name, "id"), (ast.Attribute, "attr"), (ast.arg, "arg"), (ast.keyword, "arg")}


@dataclass(frozen=True)
class _Renderer:
    """``ast.dump``-style rendering with identifier fields blanked in place.

    Walks the tree read-only via ``ast.iter_fields``, which only visits a
    node's declared ``_fields`` — the ``parent`` back-reference the engine
    attaches to every node is never one of those, so it's never touched and
    can't pull the rest of the module into the render.
    """

    preserved: set[ast.AST]

    def render(self, node: object) -> str:
        if isinstance(node, list):
            items = [self.render(item) for item in node]
            return "[" + ", ".join(items) + "]"
        if not isinstance(node, ast.AST):
            return repr(node)
        parts = []
        for name, value in ast.iter_fields(node):
            rendered = self.render(self._field_value(node, name, value))
            parts.append(f"{name}={rendered}")
        return f"{type(node).__name__}({', '.join(parts)})"

    def _field_value(self, node: ast.AST, name: str, value: object) -> object:
        """The field's value, blanked to ``"_"`` when it is an anonymized identifier."""
        is_identifier = (type(node), name) in _IDENTIFIER_FIELDS and value is not None
        return "_" if is_identifier and node not in self.preserved else value


def _normalized_dump(node: ast.AST, imported_names: set[str]) -> str:
    """Renders ``node`` with variable/parameter/attribute names blanked out.

    Two statements with identical control flow and literals but different
    names (``rows`` vs ``items``) render to the same string; called function/
    method names (with any imported-module receiver) and literal constants
    still tell them apart, so this stays conservative.
    """
    return _Renderer(_preserved_nodes(node, imported_names)).render(node)


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


def _exact_dump(node: ast.AST, imported_names: set[str]) -> str:
    """``ast.dump`` as written: identifiers are kept, so only true copies collide.

    ``imported_names`` is unused; it exists so both dump functions share one
    signature and can be passed interchangeably to ``_grouped_by_fingerprint``.
    """
    return ast.dump(node, annotate_fields=True, include_attributes=False)


_Member = tuple[ParsedFile, FunctionNode]
_Dump = Callable[[ast.AST, set[str]], str]


def _comparable_body(function: FunctionNode, min_statements: int) -> list[ast.stmt] | None:
    """The statements to fingerprint, or ``None`` if the function is exempt.

    Dunder methods, stub bodies, and bodies shorter than ``min_statements``
    are never compared; a leading docstring is stripped first.
    """
    if is_dunder(function.name):
        return None
    body = _significant_body(function)
    if len(body) < min_statements or _is_stub_body(body):
        return None
    return body


def _file_fingerprints(
    parsed: ParsedFile, min_statements: int, dump: _Dump
) -> Iterable[tuple[str, _Member]]:
    """(fingerprint, member) for every comparable function in one file."""
    imported = {name for name, _ in import_aliases(parsed.tree)}
    for function in parsed.functions:
        body = _comparable_body(function, min_statements)
        if body is None:
            continue
        key = "|".join(dump(statement, imported) for statement in body)
        yield key, (parsed, function)


def _grouped_by_fingerprint(
    files: list[ParsedFile], min_statements: int, dump: _Dump
) -> Iterable[list[_Member]]:
    """Groups of two-or-more functions whose fingerprinted bodies collide."""
    groups: dict[str, list[_Member]] = defaultdict(list)
    for parsed in files:
        for key, member in _file_fingerprints(parsed, min_statements, dump):
            groups[key].append(member)
    return [members for members in groups.values() if len(members) >= 2]


class _DuplicationRule(ProjectRule):
    """Shared reporting for rules that group functions by a body fingerprint."""

    _VERB: ClassVar[str]
    _SUGGESTION: ClassVar[str]

    def _flag_group(self, config: "Config", members: list[_Member]) -> Iterable[Violation]:
        """One violation per member after the first, pointing back at the original."""
        first_parsed, first_function = members[0]
        for parsed, function in members[1:]:
            yield self.violation(
                config,
                Location(path=parsed.path, node=function),
                ViolationDetails(
                    message=f"function `{function.name}` {self._VERB} "
                    f"`{first_function.name}` at {first_parsed.path}:{first_function.lineno}",
                    suggestion=self._SUGGESTION,
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

    _VERB = "duplicates the body of"
    _SUGGESTION = "extract the shared logic into a common helper function"

    def check_project(self, files: list[ParsedFile], config: "Config") -> Iterable[Violation]:
        min_statements = config.rules[self.id].options["min_statements"]
        for members in _grouped_by_fingerprint(files, min_statements, _normalized_dump):
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

    _VERB = "is an exact copy of"
    _SUGGESTION = "keep one copy and import/reuse it from the other location"

    def check_project(self, files: list[ParsedFile], config: "Config") -> Iterable[Violation]:
        min_statements = config.rules[self.id].options["min_statements"]
        dp701 = config.rules[DuplicateFunctionBody.id]
        for members in _grouped_by_fingerprint(files, min_statements, _exact_dump):
            if dp701.enabled and self._covered_by_dp701(members, dp701.options["min_statements"]):
                continue  # DP701 already reports this group; don't double-flag
            yield from self._flag_group(config, members)

    @staticmethod
    def _covered_by_dp701(members: list[_Member], dp701_min_statements: int) -> bool:
        _, first_function = members[0]
        return len(_significant_body(first_function)) >= dp701_min_statements
