"""Python correctness pitfalls (PY9xx).

Unlike the style/structure bands above, these rules flag shapes that are
almost never the right choice regardless of style preference — a handler
whose body is entirely inert hides a failure with no trace at all.
"""

from __future__ import annotations

import ast
from typing import Iterable

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import Rule


def _except_handlers(tree: ast.Module) -> Iterable[ast.ExceptHandler]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            yield node


def _is_inert_constant(value: ast.expr) -> bool:
    return isinstance(value, ast.Constant) and (value.value is Ellipsis or isinstance(value.value, str))


def _is_inert_statement(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Pass):
        return True
    return isinstance(statement, ast.Expr) and _is_inert_constant(statement.value)


class EmptyExceptionHandler(Rule):
    id = "PY902"
    name = "empty-exception-handler"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags an exception handler whose entire body is inert (`pass`, a bare "
        "`...`, or a lone string literal, in any combination) — the failure is "
        "silently discarded with no log, fallback, or re-raise. Handlers that "
        "`continue`/`return`/`break`, log, or re-raise are real control-flow "
        "decisions and are not flagged."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for handler in _except_handlers(ctx.tree):
            if handler.body and all(_is_inert_statement(statement) for statement in handler.body):
                yield self.violation(
                    ctx,
                    handler,
                    ViolationDetails(
                        message="exception silently discarded — handler body does "
                        "nothing to acknowledge the failure",
                        suggestion="log it, return an explicit fallback, or "
                        "re-raise — anything that leaves a trace",
                        symbol=ctx.enclosing_symbol(handler),
                    ),
                )
