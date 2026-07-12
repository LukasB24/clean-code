"""Cross-file duplication rule (DP7xx).

Unlike the per-file rules, this one is a ``ProjectRule``: it sees every parsed
file in one analysis run at once, which is the only way to catch a function
copy-pasted into another module (or another class in the same file).
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable

from cleancode.models import Location, ParsedFile, Severity, Violation, ViolationDetails
from cleancode.rules.base import FunctionNode, ProjectRule, functions

if TYPE_CHECKING:
    from cleancode.config import Config

_IDENTIFIER_FIELD = re.compile(r"(id|arg|attr)='[^']*'")


def _normalized_dump(node: ast.AST) -> str:
    """``ast.dump`` with variable/parameter/attribute names blanked out.

    Two statements with identical control flow and literals but different
    names (``rows`` vs ``items``) dump to the same string; different literal
    constants still tell them apart, so this stays conservative.
    """
    dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
    return _IDENTIFIER_FIELD.sub(r"\1='_'", dumped)


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


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


@dataclass
class _IndexState:
    min_statements: int
    groups: dict[str, list[tuple[ParsedFile, FunctionNode]]] = field(
        default_factory=lambda: defaultdict(list)
    )


class DuplicateFunctionBody(ProjectRule):
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

    def check_project(self, files: list[ParsedFile], config: "Config") -> Iterable[Violation]:
        min_statements = config.rules[self.id].options["min_statements"]
        state = _IndexState(min_statements=min_statements)
        for parsed in files:
            for function in functions(parsed.tree):
                self._index_function(function, parsed, state)
        yield from self._flag_duplicates(config, state.groups)

    def _index_function(self, function: FunctionNode, parsed: ParsedFile, state: _IndexState) -> None:
        if _is_dunder(function.name):
            return
        body = _significant_body(function)
        if len(body) < state.min_statements or _is_stub_body(body):
            return
        fingerprint = "|".join(_normalized_dump(statement) for statement in body)
        state.groups[fingerprint].append((parsed, function))

    def _flag_duplicates(
        self, config: "Config", groups: dict[str, list[tuple[ParsedFile, FunctionNode]]]
    ) -> Iterable[Violation]:
        for members in groups.values():
            if len(members) < 2:
                continue
            first_parsed, first_function = members[0]
            for parsed, function in members[1:]:
                yield self.violation(
                    config,
                    Location(path=parsed.path, node=function),
                    ViolationDetails(
                        message=f"function `{function.name}` duplicates the body of "
                        f"`{first_function.name}` at {first_parsed.path}:{first_function.lineno}",
                        suggestion="extract the shared logic into a common helper function",
                        symbol=function.name,
                    ),
                )
