"""BAD/GOOD example registry for `clean-code explain`.

One ``Example`` per rule, minimal enough to pattern-match, real enough to
actually trip the rule. ``tests/test_examples.py`` is the enforcement: every
rule must appear here, its ``bad`` must fire, and its ``good`` must not —
this doubles as a permanent regression net for every rule's behavior.
"""

from __future__ import annotations

from cleancode.examples import (
    bindings,
    clarity,
    comments,
    correctness,
    docstrings,
    duplication,
    hints,
    naming,
    noise,
    pytorch,
    semantic,
    slicing,
    solid,
    structure,
)
from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    **structure.EXAMPLES,
    **naming.EXAMPLES,
    **comments.EXAMPLES,
    **docstrings.EXAMPLES,
    **slicing.EXAMPLES,
    **hints.EXAMPLES,
    **semantic.EXAMPLES,
    **pytorch.EXAMPLES,
    **bindings.EXAMPLES,
    **clarity.EXAMPLES,
    **noise.EXAMPLES,
    **solid.EXAMPLES,
    **duplication.EXAMPLES,
    **correctness.EXAMPLES,
}

__all__ = ["Example", "EXAMPLES"]
