"""Rule base class and text helpers shared across rule modules."""

from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Iterable, Iterator

from cleancode.models import Location, Positioned, Severity, Violation, ViolationDetails

if TYPE_CHECKING:
    from cleancode.config import Config
    from cleancode.models import FileContext, ParsedFile

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def functions(tree: ast.Module) -> Iterator[FunctionNode]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def subscript_base_name(node: ast.Subscript) -> str | None:
    """The name a subscript's ``.value`` resolves to: ``x[...]`` -> ``"x"``, ``a.b[...]`` -> ``"b"``."""
    value = node.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def import_aliases(tree: ast.Module) -> Iterator[tuple[str, ast.alias]]:
    """(bound name, alias node) for every import in the module, ``__future__`` excluded."""
    for node in ast.walk(tree):
        yield from _aliases_of(node)


def _aliases_of(node: ast.AST) -> Iterator[tuple[str, ast.alias]]:
    if isinstance(node, ast.Import):
        aliases = node.names
        return ((alias.asname or alias.name.split(".")[0], alias) for alias in aliases)
    if isinstance(node, ast.ImportFrom) and node.module != "__future__":
        aliases = node.names
        return ((alias.asname or alias.name, alias) for alias in aliases if alias.name != "*")
    return iter(())


SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def own_scope_walk(
    node: ast.AST, boundaries: tuple[type[ast.AST], ...] = SCOPE_BOUNDARIES
) -> Iterator[ast.AST]:
    """Descendants of ``node`` in its own scope — nested scopes are skipped.

    Each nested function/class is checked independently when a rule reaches
    it; walking into it here would attribute its nodes to the wrong scope.
    Pass a narrower ``boundaries`` tuple to keep some nested scopes in the
    walk (e.g. lambdas, which never get their own per-function score).
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        child = stack.pop()
        if isinstance(child, boundaries):
            continue
        yield child
        stack.extend(ast.iter_child_nodes(child))


def is_elif_branch(statement: ast.stmt) -> bool:
    """True for the `elif` branches of an if-chain, which the AST nests in orelse.

    A hand-written `else:\\n    if ...` sits one indent deeper, so the column
    offset distinguishes it from `elif` (which shares the parent's column).
    """
    parent = getattr(statement, "parent", None)
    return (
        isinstance(statement, ast.If)
        and isinstance(parent, ast.If)
        and parent.orelse == [statement]
        and statement.col_offset == parent.col_offset
    )


class Rule(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    default_options: ClassVar[dict[str, Any]]
    description: ClassVar[str]

    @abstractmethod
    def check(self, ctx: "FileContext") -> Iterable[Violation]: ...

    def violation(self, ctx: "FileContext", node: Positioned, details: ViolationDetails) -> Violation:
        return Violation(
            rule_id=self.id,
            rule_name=self.name,
            message=details.message,
            line=node.lineno,
            col=node.col_offset,
            severity=ctx.config.severity,
            suggestion=details.suggestion,
            symbol=details.symbol,
        )


class ProjectRule(ABC):
    """A rule that compares code across every file in one analysis run.

    Unlike ``Rule``, which sees one file at a time, ``check_project`` receives
    every parsed file up front — the only way to catch cross-file DRY/SOLID
    smells like duplicate function bodies.
    """

    id: ClassVar[str]
    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    default_options: ClassVar[dict[str, Any]]
    description: ClassVar[str]

    @abstractmethod
    def check_project(
        self, files: list["ParsedFile"], config: "Config"
    ) -> Iterable[Violation]: ...

    def violation(self, config: "Config", location: Location, details: ViolationDetails) -> Violation:
        return Violation(
            rule_id=self.id,
            rule_name=self.name,
            message=details.message,
            line=location.node.lineno,
            col=location.node.col_offset,
            severity=config.rules[self.id].severity,
            suggestion=details.suggestion,
            symbol=details.symbol,
            path=location.path,
        )


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_WORD = re.compile(r"[^a-z0-9']+")

# Words that carry no information when comparing comments/docstrings to code.
STOPWORDS = frozenset(
    """
    a an the this that these those it its of to in on at by for and or nor as with
    from is are was were be been being will would shall should can could may might
    must did have has had having we you i they he she one
    all each any some no not if then when while
    over through using per via up down out off into onto also just simply now
    here there new current
    """.split()
)

# Words LLM docstrings use to frame a restatement of the function name
# ("Gets the value.", "Do the thing."). Stripped before overlap scoring in the
# docstring rules, but still visible to the comment rules.
FRAMING_VERBS = frozenset(
    """
    get gets set sets compute computes calculate calculates process processes
    handle handles perform performs execute executes run runs make makes create
    creates take takes use uses call calls define defines implement implements
    check checks do does doing done thing things stuff
    given return returns returning function method value values result results
    """.split()
)


def split_identifier(name: str) -> list[str]:
    """Split a snake_case / camelCase / PascalCase identifier into lowercase words.

    ``get_user_name`` -> ``["get", "user", "name"]``;
    ``HTTPResponseParser`` -> ``["http", "response", "parser"]``.
    """
    words: list[str] = []
    for chunk in name.split("_"):
        words.extend(word.lower() for word in _CAMEL_BOUNDARY.split(chunk) if word)
    return words


def content_words(text: str, extra_stopwords: frozenset[str] = frozenset()) -> set[str]:
    """Lowercased informative words of free text: punctuation and stopwords removed."""
    words = _NON_WORD.split(text.lower())
    return {
        word.strip("'")
        for word in words
        if word.strip("'") and word not in STOPWORDS and word not in extra_stopwords
    }
