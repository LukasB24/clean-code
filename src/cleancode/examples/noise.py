"""BAD/GOOD examples for the naming/indirection-ceremony rules (SM620-SM622)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SM620": Example(
        bad="def compute(x):\n    result = x * 2\n    return result\n",
        good="def compute(x):\n    return x * 2\n",
        note="An annotated assignment (`result: int = x * 2`) is exempt — the annotation is informative.",
    ),
    "SM621": Example(
        bad="def helper():\n    pass\n\n\nold_helper = helper\n",
        good="def helper():\n    pass\n",
        note="ALL_CAPS and `_`-prefixed targets, and annotated assignments (`TypeAlias`), are exempt.",
    ),
    "SM622": Example(
        bad=(
            "class Point:\n"
            "    def __init__(self, x):\n"
            "        self._x = x\n"
            "\n"
            "    @property\n"
            "    def x(self):\n"
            "        return self._x\n"
            "\n"
            "    @x.setter\n"
            "    def x(self, value):\n"
            "        self._x = value\n"
        ),
        good=(
            "class Point:\n"
            "    def __init__(self, x):\n"
            "        self.x = x\n"
        ),
        note="A getter-only read-only property, or either accessor doing real work, is exempt.",
    ),
}
