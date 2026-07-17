"""BAD/GOOD examples for the naming rules (NM2xx)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "NM201": Example(
        bad="def f(x):\n    return x\n",
        good="def format_price(amount):\n    return amount\n",
        note="Conventional loop/comprehension letters (i, j, k, n, x, y) stay exempt.",
    ),
    "NM202": Example(
        bad="def process_data(data):\n    return data\n",
        good="def parse_trades(csv_rows):\n    return csv_rows\n",
        note="ALL_CAPS constants (INFO, DEFAULT) are named by convention and exempt.",
    ),
    "NM203": Example(
        bad="usr_mgr = get_manager()\n",
        good="user_manager = get_manager()\n",
        note="Only vowel-less parts are flagged; `usr` (has a vowel) passes, `mgr` doesn't.",
    ),
}
