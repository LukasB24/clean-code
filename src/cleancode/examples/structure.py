"""BAD/GOOD examples for the structure rules (ST1xx)."""

from __future__ import annotations

from cleancode.examples._types import Example
from cleancode.examples._util import numbered_methods, numbered_statements

EXAMPLES: dict[str, Example] = {
    "ST101": Example(
        bad=(
            "def process(rows):\n"
            "    for row in rows:\n"
            "        if row.active:\n"
            "            if row.total > 0:\n"
            "                print(row.total)\n"
        ),
        good=(
            "def process(rows):\n"
            "    for row in rows:\n"
            "        if _is_valid(row):\n"
            "            print(row.total)\n"
            "\n"
            "\n"
            "def _is_valid(row):\n"
            "    return row.active and row.total > 0\n"
        ),
        note="elif branches don't add depth; only if/for/while/with/try nesting does.",
    ),
    "ST102": Example(
        bad=(
            "def compute_total(rows):\n"
            "    total = 0\n" + numbered_statements(61) + "\n    return total\n"
        ),
        good="def compute_total(rows):\n    return sum(rows)\n",
        note="Length includes the docstring; blank lines inside the body still count.",
    ),
    "ST103": Example(
        bad="class ReportBuilder:\n" + numbered_methods(105),
        good=(
            "class Report:\n"
            "    def __init__(self):\n"
            "        self.rows = []\n"
            "\n"
            "    def add_row(self, row):\n"
            "        self.rows.append(row)\n"
        ),
        note="A class that keeps absorbing helper methods over time; split by responsibility.",
    ),
    "ST104": Example(
        bad="def create_user(name, email, age, country, is_admin):\n    pass\n",
        good="def create_user(profile: UserProfile):\n    pass\n",
        note="self/cls, *args, and **kwargs don't count toward the limit.",
    ),
    "ST105": Example(
        bad=(
            "def classify(n):\n"
            "    if n == 0:\n"
            '        return "zero"\n'
            "    elif n == 1:\n"
            '        return "one"\n'
            "    elif n == 2:\n"
            '        return "two"\n'
            "    elif n == 3:\n"
            '        return "three"\n'
            "    elif n == 4:\n"
            '        return "four"\n'
            "    elif n == 5:\n"
            '        return "five"\n'
            "    elif n == 6:\n"
            '        return "six"\n'
            "    elif n == 7:\n"
            '        return "seven"\n'
            "    elif n == 8:\n"
            '        return "eight"\n'
            "    elif n == 9:\n"
            '        return "nine"\n'
            "    elif n == 10:\n"
            '        return "ten"\n'
            '    return "many"\n'
        ),
        good=(
            '_NAMES = {0: "zero", 1: "one", 2: "two", 3: "three"}\n'
            "\n"
            "\n"
            "def classify(n):\n"
            '    return _NAMES.get(n, "many")\n'
        ),
        note="Each elif, for, while, except, ternary, and extra and/or operand adds one.",
    ),
    "ST106": Example(
        bad=(
            "def load_and_save(path):\n"
            "    data = read(path)\n"
            "    write(data)\n"
        ),
        good=(
            "def load(path):\n"
            "    return read(path)\n"
            "\n"
            "\n"
            "def save(data):\n"
            "    write(data)\n"
        ),
    ),
    "ST107": Example(
        bad=(
            "def process(row):\n"
            "    if row is None:\n"
            "        return None\n"
            "    if not row.active:\n"
            "        return None\n"
            "    if row.total < 0:\n"
            "        return None\n"
            "    return row.total\n"
        ),
        good=(
            "def process(row):\n"
            "    if not _is_valid(row):\n"
            "        return None\n"
            "    return row.total\n"
            "\n"
            "\n"
            "def _is_valid(row):\n"
            "    return row is not None and row.active and row.total >= 0\n"
        ),
        note="A guard clause is `if cond: continue/return/raise/break` with no else.",
    ),
    "ST108": Example(
        bad=numbered_statements(501, indent=""),
        good='def greet(name):\n    return f"hello {name}"\n',
        note="Counts blank lines and comments too, mirroring how a reader scrolls the file.",
    ),
    "ST109": Example(
        bad=(
            "def classify(n):\n"
            '    if n < 0:\n'
            '        return "negative"\n'
            "    else:\n"
            '        return "non-negative"\n'
        ),
        good=(
            "def classify(n):\n"
            '    if n < 0:\n'
            '        return "negative"\n'
            '    return "non-negative"\n'
        ),
        note="Any `if` that's itself part of an `elif` chain is exempt — a multi-way dispatch ladder is idiomatic.",
    ),
}
