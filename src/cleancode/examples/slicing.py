"""BAD/GOOD examples for the subscript-complexity rules (SL4xx)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SL401": Example(
        bad="window = data[i : i + 5 : 2, None, idx[j]]\n",
        good="row = data[i]\n",
        note="Type annotations like `dict[str, int]` are never scored.",
    ),
    "SL402": Example(
        bad="value = grid[i][j][k]\n",
        good="value = grid[i, j, k]\n",
        note="Multi-dimensional indexing (`grid[i, j, k]`) isn't a chain at all.",
    ),
}
