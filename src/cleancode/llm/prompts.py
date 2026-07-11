"""Prompt construction: system prompt and violation-to-feedback rendering."""

from __future__ import annotations

from cleancode.config import Config
from cleancode.models import CheckResult

_SYSTEM_TEMPLATE = """\
You are writing production Python that a human must be able to review quickly.

Hard requirements for every reply:
- Output exactly ONE fenced ```python code block and nothing else — no prose \
before or after it.
- The block must contain the complete, runnable file.
- Do not use `# cleancode: disable` or any other lint-suppression comment.
- Comments and docstrings are allowed only when they say something the code \
cannot: why, edge cases, units, invariants. Never narrate what a line does.

Your code is checked automatically against these readability rules:
{rules}
"""


def build_system_prompt(config: Config) -> str:
    from cleancode.rules import ALL_RULES

    rendered = []
    for rule in ALL_RULES:
        rule_config = config.rules[rule.id]
        if not rule_config.enabled:
            continue
        options = ", ".join(f"{key}={value}" for key, value in rule_config.options.items())
        rendered.append(f"- {rule.id} {rule.name} ({options}): {rule.description}")
    return _SYSTEM_TEMPLATE.format(rules="\n".join(rendered))


def render_feedback(check_result: CheckResult, code: str) -> str:
    """Serialize a check result into the refinement message for the next round."""
    if check_result.parse_error:
        return (
            f"Your code does not parse: {check_result.parse_error}.\n"
            "Return the complete corrected file as one ```python block."
        )

    lines = code.splitlines()
    header = (
        f"Your code has {len(check_result.violations)} readability violation(s). "
        "Fix ALL of them and return the complete corrected file as one "
        "```python block. Do not add comments explaining the fixes, and do not "
        "use suppression comments.\n"
    )
    entries = []
    for index, violation in enumerate(check_result.violations, start=1):
        source_line = ""
        if 1 <= violation.line <= len(lines):
            source_line = f"\n   > {lines[violation.line - 1].strip()}"
        where = f"line {violation.line}"
        if violation.symbol:
            where += f", in `{violation.symbol}`"
        entry = (
            f"{index}. [{violation.rule_id} {violation.rule_name}] {where}:"
            f"{source_line}\n   {violation.message}."
        )
        if violation.suggestion:
            entry += f"\n   Fix: {violation.suggestion}."
        entries.append(entry)
    return header + "\n".join(entries)
