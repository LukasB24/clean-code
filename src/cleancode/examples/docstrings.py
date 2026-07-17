"""BAD/GOOD examples for the docstring-noise rules (CM301, CM304)."""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "CM301": Example(
        bad=(
            "def get_user_name(user):\n"
            '    """Gets the user name."""\n'
            "    return user.name\n"
        ),
        good=(
            "def get_user_name(user):\n"
            '    """Falls back to the signup name if the profile name was never set."""\n'
            "    return user.name\n"
        ),
        note="A docstring longer than two lines is judged: does every line stay within the signature vocabulary?",
    ),
    "CM304": Example(
        bad=(
            "def transform(data, factor):\n"
            '    """Transforms data.\n'
            "\n"
            "    Args:\n"
            "        data: The data.\n"
            "        factor: The factor.\n"
            '    """\n'
            "    return data * factor\n"
        ),
        good=(
            "def transform(data, factor):\n"
            '    """Transforms data.\n'
            "\n"
            "    Args:\n"
            "        data: Rows already deduplicated by the caller; never empty.\n"
            "        factor: Multiplier in (0, 1]; values outside raise ValueError.\n"
            '    """\n'
            "    return data * factor\n"
        ),
        note="An entry is uninformative when its words never leave the parameter's own name.",
    ),
}
