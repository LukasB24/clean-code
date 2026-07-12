"""Rule base class and text helpers shared across rule modules."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Iterable

from cleancode.models import Severity, Violation

if TYPE_CHECKING:
    from cleancode.models import FileContext


class Rule(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    default_severity: ClassVar[Severity]
    default_options: ClassVar[dict[str, Any]]
    description: ClassVar[str]

    @abstractmethod
    def check(self, ctx: "FileContext") -> Iterable[Violation]: ...

    def violation(  # cleancode: disable=ST104
        self,
        ctx: "FileContext",
        message: str,
        line: int,
        col: int,
        suggestion: str | None = None,
        symbol: str | None = None,
    ) -> Violation:
        return Violation(
            rule_id=self.id,
            rule_name=self.name,
            message=message,
            line=line,
            col=col,
            severity=ctx.config.severity,
            suggestion=suggestion,
            symbol=symbol,
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
