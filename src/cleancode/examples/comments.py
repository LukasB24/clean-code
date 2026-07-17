"""BAD/GOOD examples for the comment-noise rules (CM302, CM303, CM305)."""

from __future__ import annotations

from cleancode.examples._types import Example
from cleancode.examples._util import numbered_statements

EXAMPLES: dict[str, Example] = {
    "CM302": Example(
        bad="x = x + 1  # increment x by one\n",
        good="x = x + 1  # compensate for the off-by-one error in the legacy API\n",
        note="A causal marker (because, workaround, legacy, ...) exempts a comment outright.",
    ),
    "CM303": Example(
        bad=(
            "def compute(a, b, c, d, e):\n"
            "    # start work\n"
            "    total = a + b\n"
            "    # continue work\n"
            "    total += c\n"
            "    # more work\n"
            "    total += d\n"
            "    # finish\n"
            "    total += e\n"
            "    return total\n"
        ),
        good=(
            "def compute(a, b, c, d, e):\n"
            "    total = a + b\n"
            "    total += c\n"
            "    total += d\n"
            "    total += e\n"
            "    return total\n"
        ),
        note="Docstrings are policed separately by CM301/CM304, not counted here.",
    ),
    "CM305": Example(
        bad=numbered_statements(32, comment_every=4),
        good='def greet(name):\n    return f"hello {name}"\n',
        note="Files under `min_code_lines` (default 30) are never flagged, however dense.",
    ),
}
