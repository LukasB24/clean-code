"""BAD/GOOD examples for the SOLID-adjacent rules (SD8xx)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SD801": Example(
        bad=(
            "def render(shape):\n"
            "    if isinstance(shape, Circle):\n"
            "        return draw_circle(shape)\n"
            "    elif isinstance(shape, Square):\n"
            "        return draw_square(shape)\n"
            "    elif isinstance(shape, Triangle):\n"
            "        return draw_triangle(shape)\n"
            "    return None\n"
        ),
        good="def render(shape):\n    return shape.draw()\n",
        note="Dispatching on Python's own `ast.*` node types is exempt as routine AST tooling.",
    ),
    "SD802": Example(
        bad=(
            "class ReportAndMailer:\n"
            "    def __init__(self):\n"
            "        self.rows = []\n"
            "        self.smtp = None\n"
            "\n"
            "    def add_row(self, row):\n"
            "        self.rows.append(row)\n"
            "\n"
            "    def render(self):\n"
            '        return "\\n".join(self.rows)\n'
            "\n"
            "    def connect(self, host):\n"
            "        self.smtp = host\n"
            "\n"
            "    def send(self, message):\n"
            "        self.smtp.sendmail(message)\n"
        ),
        good=(
            "class Report:\n"
            "    def __init__(self):\n"
            "        self.rows = []\n"
            "\n"
            "    def add_row(self, row):\n"
            "        self.rows.append(row)\n"
            "\n"
            "    def render(self):\n"
            '        return "\\n".join(self.rows)\n'
        ),
        note="A class named with an `exempt_name_suffixes` suffix (default `Mixin`) is exempt entirely.",
    ),
}
