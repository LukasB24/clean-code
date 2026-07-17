"""BAD/GOOD examples for the binding-level rules (SM611-SM613)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SM611": Example(
        bad=(
            "def describe(value: int):\n"
            '    if isinstance(value, int):\n'
            '        return "integer"\n'
            '    return "other"\n'
        ),
        good=(
            "def describe(value: int | str):\n"
            '    if isinstance(value, int):\n'
            '        return "integer"\n'
            '    return "other"\n'
        ),
        note="Only a *simple*, exact-match annotation is redundant — a union type still needs the check.",
    ),
    "SM612": Example(
        bad=(
            "import json\n"
            "\n"
            "\n"
            "def parse(raw):\n"
            "    data = json.loads(raw)\n"
            "    return None\n"
        ),
        good=(
            "import json\n"
            "\n"
            "\n"
            "def parse(raw):\n"
            "    data = json.loads(raw)\n"
            "    return data\n"
        ),
        note="Prefix with `_` to keep an intentionally discarded value without triggering this.",
    ),
    "SM613": Example(
        bad="def make_list(id):\n    list = [id]\n    return list\n",
        good="def make_list(item_id):\n    values = [item_id]\n    return values\n",
        note="Only a configurable `watched` list of builtins is checked, not every builtin.",
    ),
}
