"""Python correctness pitfalls (PY9xx).

Unlike the style/structure bands above, these rules flag shapes that are
almost never the right choice regardless of style preference — a bare
``except:`` swallows ``KeyboardInterrupt``/``SystemExit`` along with real
bugs.
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
