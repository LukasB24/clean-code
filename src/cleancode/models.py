"""Core data model shared by the rule engine, CLI, and LLM loop."""

from __future__ import annotations

import ast
import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cleancode.config import RuleConfig


class Severity(enum.IntEnum):
    INFO = 10
    WARNING = 20
    ERROR = 30

    @classmethod
    def from_name(cls, name: str) -> "Severity":
        try:
            return cls[name.upper()]
        except KeyError:
            valid = ", ".join(level.name.lower() for level in cls)
            raise ValueError(f"unknown severity {name!r}; expected one of: {valid}") from None


@dataclass(frozen=True)
class Violation:
    rule_id: str
    rule_name: str
    message: str
    line: int
    col: int
    severity: Severity
    suggestion: str | None = None
    symbol: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "message": self.message,
            "line": self.line,
            "col": self.col,
            "severity": self.severity.name.lower(),
            "suggestion": self.suggestion,
            "symbol": self.symbol,
        }


@dataclass
class CheckResult:
    path: str
    violations: list[Violation] = field(default_factory=list)
    parse_error: str | None = None

    @property
    def ok(self) -> bool:
        return self.parse_error is None and not self.violations

    def max_severity(self) -> Severity | None:
        if not self.violations:
            return None
        return max(violation.severity for violation in self.violations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "parse_error": self.parse_error,
            "violations": [violation.to_dict() for violation in self.violations],
        }


@dataclass(frozen=True)
class Comment:
    """A ``#`` comment extracted via tokenize, with the leading ``#`` stripped."""

    line: int
    col: int
    text: str
    inline: bool  # shares its line with code (as opposed to a standalone comment line)


@dataclass
class FileContext:
    """Everything a rule needs to inspect one parsed file."""

    path: str
    source: str
    lines: list[str]
    tree: ast.Module
    comments: list[Comment]
    config: "RuleConfig"

    def enclosing_symbol(self, node: ast.AST) -> str | None:
        """Dotted name of the innermost function/class containing ``node``."""
        parts: list[str] = []
        current = getattr(node, "parent", None)
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                parts.append(current.name)
            current = getattr(current, "parent", None)
        return ".".join(reversed(parts)) or None
