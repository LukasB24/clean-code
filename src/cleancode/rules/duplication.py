"""Cross-file duplication rule (DP7xx).

Unlike the per-file rules, this one is a ``ProjectRule``: it sees every parsed
file in one analysis run at once, which is the only way to catch a function
copy-pasted into another module (or another class in the same file).
"""

from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass
from functools import partial
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

    Reads the tree without copying or mutating it. ``copy.deepcopy`` is off
    the table here: the engine attaches a ``parent`` back-reference to every
    node, so deep-copying one statement would drag the entire module graph
    into every copy — quadratic, and the dominant cost of a whole check run.
    """

    preserved: set[ast.AST]

    def render(self, node: object) -> str:
        if isinstance(node, list):
            return "[" + ", ".join(self.render(item) for item in node) + "]"
        if not isinstance(node, ast.AST):
            return repr(node)
        fields = ", ".join(
            f"{name}={self.render(self._field_value(node, name, value))}"
            for name, value in ast.iter_fields(node)
        )
        return f"{type(node).__name__}({fields})"

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
    for function in parsed.functions:
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
