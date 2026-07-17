"""Python correctness pitfalls (PY9xx).

Unlike the style/structure bands above, these rules flag shapes that are
almost never the right choice regardless of style preference — a bare
``except:`` swallows ``KeyboardInterrupt``/``SystemExit`` along with real
bugs, and a handler whose body is entirely inert hides a failure with no
trace at all.
"""

from __future__ import annotations

import ast
from typing import Iterable

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import Rule, simple_name


def _except_handlers(tree: ast.Module) -> Iterable[ast.ExceptHandler]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            yield node


class BareExcept(Rule):
    id = "PY901"
    name = "bare-except"
    default_severity = Severity.WARNING
    default_options: dict = {}
    description = (
        "Flags `except:` with no exception type at all — it catches "
        "`KeyboardInterrupt` and `SystemExit` along with genuine bugs, silently "
        "absorbing signals that should propagate. `except Exception:` is merely "
        "broad, not bare, and is not flagged."
    )
    guidance = (
        "Never write a bare `except:` — name the expected exception(s) explicitly "
        "(`except (ValueError, KeyError):`)."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        for handler in _except_handlers(ctx.tree):
            if handler.type is not None:
                continue
            yield self.violation(
                ctx,
                handler,
                ViolationDetails(
                    message="bare `except:` catches everything, including "
                    "KeyboardInterrupt and SystemExit",
                    suggestion="name the expected exception(s), e.g. "
                    "`except (ValueError, KeyError):`",
                    symbol=ctx.enclosing_symbol(handler),
                ),
            )


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
    guidance = (
        "Never leave an exception handler's body inert (`pass`, `...`, a lone "
        "string) — log it, return an explicit fallback, or re-raise."
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


_BROAD_EXCEPTION_NAMES = frozenset({"Exception", "BaseException"})


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return simple_name(handler.type) in _BROAD_EXCEPTION_NAMES


class OversizedTry(Rule):
    id = "PY903"
    name = "oversized-try"
    default_severity = Severity.WARNING
    default_options = {"max_statements": 3}
    description = (
        "Flags a `try` block with more than `max_statements` top-level "
        "statements feeding a bare or `except Exception`/`BaseException` "
        "handler — the handler can't know which of several steps actually "
        "failed. A `try` narrowed to a specific exception, or a broad handler "
        "wrapping few statements, is not flagged."
    )
    guidance = (
        "Narrow a `try` to the statement(s) that can actually raise, or name "
        "the specific exception each step raises, before writing a "
        "bare/broad `except`."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        max_statements = ctx.config.options["max_statements"]
        for node in ast.walk(ctx.tree):
            if not isinstance(node, (ast.Try, ast.TryStar)):
                continue
            if len(node.body) <= max_statements or not any(
                _is_broad_handler(handler) for handler in node.handlers
            ):
                continue
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message=f"`try` spans {len(node.body)} statements feeding a "
                    "broad `except` — the handler cannot know which step failed",
                    suggestion="narrow the try to the statement(s) that can "
                    "raise, or name the specific exception each step raises",
                    symbol=ctx.enclosing_symbol(node),
                ),
            )
