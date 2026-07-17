"""The shared value type every band's ``EXAMPLES`` dict is built from."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    """A minimal BAD/GOOD pair for one rule, for `clean-code explain`."""

    bad: str
    good: str
    note: str | None = None
