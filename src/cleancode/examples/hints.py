"""BAD/GOOD examples for the type-hint rule (TY5xx)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "TY501": Example(
        bad=(
            "from typing import Any\n"
            "\n"
            "\n"
            "def handle(payload: Any) -> None:\n"
            "    pass\n"
        ),
        good=(
            "from typing import Any\n"
            "\n"
            "\n"
            "def handle(payload: dict[str, Any]) -> None:\n"
            "    pass\n"
        ),
        note="`Any` nested in a container payload (`dict[str, Any]`) is a justified exception.",
    ),
}
