"""BAD/GOOD examples for the expression-clarity rules (SM614-SM619)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SM614": Example(
        bad=(
            "count = 0\n"
            "for value in values:\n"
            "    count += value in seen\n"
        ),
        good=(
            "count = 0\n"
            "for value in values:\n"
            "    if value in seen:\n"
            "        count += 1\n"
        ),
        note="Deliberately narrow to augmented assignments, so numpy/torch mask arithmetic is untouched.",
    ),
    "SM615": Example(
        bad='label = "high" if score > 90 else ("medium" if score > 50 else "low")\n',
        good=(
            "if score > 90:\n"
            '    label = "high"\n'
            "elif score > 50:\n"
            '    label = "medium"\n'
            "else:\n"
            '    label = "low"\n'
        ),
        note=None,
    ),
    "SM616": Example(
        bad="def make_validator():\n    return lambda value: value > 0\n",
        good="def is_positive(value):\n    return value > 0\n",
        note="Returning a nested `def` (the decorator shape) is not flagged.",
    ),
    "SM617": Example(
        bad="def run(x):\n    return f(g(h(i(j(k(x))))))\n",
        good=(
            "def run(x):\n"
            "    step1 = k(x)\n"
            "    step2 = j(step1)\n"
            "    return f(step2)\n"
        ),
        note="Only checked inside functions; module-level constant tables are exempt.",
    ),
    "SM618": Example(
        bad="def _load_config(path):\n    return read_config_file(path)\n",
        good="def _load_config(path):\n    raw = read_config_file(path)\n    return normalize(raw)\n",
        note="Public functions, decorated functions, dunders, and builtin one-liners are exempt.",
    ),
    "SM619": Example(
        bad="end = (node.end_lineno or node.lineno) + 1\n",
        good="raw_end = node.end_lineno or node.lineno\nend = raw_end + 1\n",
        note="A bare `x = a or b` and ordinary boolean conditions (`if`/`while`) stay exempt.",
    ),
}
