"""Generate a fully-commented reference config from the rule registry.

Kept in sync with the rules automatically: the template is rendered from
``ALL_RULES`` rather than hand-maintained, so a new rule or changed default
shows up here without anyone remembering to edit a static file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from cleancode.rules.base import Rule

_HEADER = """\
# CleanCode configuration reference.
#
# Every rule is enabled by default. To customize, copy the entries you want
# into your project's pyproject.toml (keeping the [tool.cleancode...] headers)
# and uncomment them. Unknown rule ids or option keys are rejected, so typos
# cannot silently disable a rule.

[tool.cleancode]
# fail_on = "warning"   # info | warning | error: lowest severity that fails a run
# disable = []          # rule ids to turn off entirely, e.g. ["NM203"]
# exclude = []          # extra glob patterns to skip, e.g. ["migrations/**"]
"""


def build_config_template() -> str:
    """Render the reference ``[tool.cleancode]`` config as commented TOML."""
    from cleancode.rules import ALL_RULES

    blocks = [_HEADER]
    for rule in ALL_RULES:
        blocks.append(_render_rule(rule))
    return "\n".join(blocks) + "\n"


def _render_rule(rule: type[Rule]) -> str:
    severity = rule.default_severity.name.lower()
    lines = [
        f"# {rule.id}  {rule.name}  [{severity}]",
        f"#   {rule.description}",
        f"# [tool.cleancode.{rule.id}]",
    ]
    for option, value in rule.default_options.items():
        lines.append(f"# {option} = {_toml_literal(value)}")
    return "\n".join(lines) + "\n"


_SCALAR_LITERALS: dict[type, Callable[[object], str]] = {
    bool: lambda value: "true" if value else "false",
    str: lambda value: f'"{value}"',
}


def _toml_literal(value: object) -> str:
    """Render a Python default as the TOML literal a user would type."""
    render = _SCALAR_LITERALS.get(type(value))
    if render is not None:
        return render(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    return str(value)
