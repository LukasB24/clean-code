"""BAD/GOOD examples for the cross-file duplication rules (DP7xx).

Both rules are ``ProjectRule``s: they only fire when the example is analyzed
as a project (``analyze_paths``), not a single source string
(``analyze_source``) — see how ``tests/test_examples.py`` runs these two.
"""

from __future__ import annotations

from cleancode.examples._types import Example

EXAMPLES: dict[str, Example] = {
    "DP701": Example(
        bad=(
            "def load_active_users(path):\n"
            "    rows = read_csv(path)\n"
            '    users = [row for row in rows if row["active"]]\n'
            '    sorted_users = sorted(users, key=lambda row: row["name"])\n'
            "    return sorted_users\n"
            "\n"
            "\n"
            "def load_active_accounts(path):\n"
            "    rows = read_csv(path)\n"
            '    accounts = [row for row in rows if row["active"]]\n'
            '    sorted_accounts = sorted(accounts, key=lambda row: row["name"])\n'
            "    return sorted_accounts\n"
        ),
        good=(
            "def _select_active(rows):\n"
            '    return sorted((row for row in rows if row["active"]), key=lambda row: row["name"])\n'
            "\n"
            "\n"
            "def load_active_users(path):\n"
            "    return _select_active(read_csv(path))\n"
            "\n"
            "\n"
            "def load_active_accounts(path):\n"
            "    return _select_active(read_csv(path))\n"
        ),
        note="Called function/method names still tell bodies apart — only variable/parameter names are anonymized.",
    ),
    "DP702": Example(
        bad=(
            "def is_valid_email(value):\n"
            '    if "@" not in value:\n'
            "        return False\n"
            "    return True\n"
            "\n"
            "\n"
            "def is_valid_username(value):\n"
            '    if "@" not in value:\n'
            "        return False\n"
            "    return True\n"
        ),
        good=(
            "def is_valid_email(value):\n"
            '    return "@" in value\n'
            "\n"
            "\n"
            "def is_valid_username(value):\n"
            "    return bool(value)\n"
        ),
        note="Identifiers must match exactly too — this catches shorter copy-pastes DP701's 4-statement floor misses.",
    ),
}
