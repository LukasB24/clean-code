"""BAD/GOOD examples for the semantic-pattern rules (SM601-SM608)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "SM601": Example(
        bad=(
            "rows = [\n"
            "    [item for item in group if (item.active if group.strict else True)]\n"
            "    for group in batches\n"
            "]\n"
        ),
        good=(
            "rows = [\n"
            "    [item for item in group if item.active]\n"
            "    for group in batches\n"
            "]\n"
        ),
        note=None,
    ),
    "SM602": Example(
        bad=(
            "def midpoint(bounds: tuple[int, int]):\n"
            "    return bounds[0] + bounds[1]\n"
        ),
        good=(
            "def midpoint(bounds: tuple[int, int]):\n"
            "    low, high = bounds\n"
            "    return low + high\n"
        ),
        note="Variadic `tuple[T, ...]` parameters are exempt — there's no fixed shape to name.",
    ),
    "SM603": Example(
        bad='label = "transaction" if key.startswith("tx_") else "other"\n',
        good=(
            'is_transaction = key.startswith("tx_")\n'
            'label = "transaction" if is_transaction else "other"\n'
        ),
        note=None,
    ),
    "SM604": Example(
        bad="is_match = True if left == right else False\n",
        good="is_match = left == right\n",
        note=None,
    ),
    "SM605": Example(
        bad=(
            "from functools import reduce\n"
            "\n"
            "total = reduce(lambda a, b: a + b, numbers)\n"
        ),
        good="total = sum(numbers)\n",
        note="`''.join(parts)` is the equivalent replacement when concatenating strings.",
    ),
    "SM606": Example(
        bad=(
            "def summarize(batch):\n"
            '    names = [item["name"] for item in batch["rows"]]\n'
            '    totals = [item["total"] for item in batch["rows"]]\n'
            "    return names, totals\n"
        ),
        good=(
            "def summarize(batch):\n"
            '    rows = batch["rows"]\n'
            '    names = [item["name"] for item in rows]\n'
            '    totals = [item["total"] for item in rows]\n'
            "    return names, totals\n"
        ),
        note="A bare local variable feeding a second comprehension is an ordinary filter, not a repeat pass.",
    ),
    "SM607": Example(
        bad="price_with_tax = price * 1.2\n",
        good=(
            "TAX_MULTIPLIER = 1.2\n"
            "\n"
            "price_with_tax = price * TAX_MULTIPLIER\n"
        ),
        note="The default `ignore` list (0, 1, -1, 2, 10) exempts domain-agnostic values.",
    ),
    "SM608": Example(
        bad="if len(rows) > 0:\n    process(rows)\n",
        good="if rows:\n    process(rows)\n",
        note=None,
    ),
}
