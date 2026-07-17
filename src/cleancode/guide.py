"""Generate a generation-time briefing from the rule registry.

Unlike ``template.py`` (a reference of every default, for editing config),
this renders an *imperative* brief meant to sit in front of an LLM before it
writes a line of Python: one bullet per enabled rule, phrased as "write it
this way", using the project's own configured option values so a loosened
`max_depth` or a disabled rule shows up correctly. Kept in sync with the
rule registry the same way ``template.py`` is — rendered from ``ALL_RULES``,
never hand-maintained.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cleancode.config import Config
    from cleancode.rules.base import ProjectRule, Rule

# A rule whose ``guidance`` is ``None`` is deliberately covered by a sibling
# rule's bullet (e.g. DP702 is the "exact copy" special case of DP701's
# "never copy-paste" guidance) — it contributes nothing of its own rather
# than repeating the same instruction twice. Every rule must define
# non-``None`` guidance or appear here; ``tests/test_guide.py`` enforces it.
COVERED_BY_SIBLING: dict[str, str] = {
    "DP702": "DP701",
}

_BAND_TITLES: dict[str, str] = {
    "ST": "Structure",
    "NM": "Naming",
    "CM": "Comments & docstrings",
    "SL": "Subscripts & types",
    "TY": "Subscripts & types",
    "SM": "Expressions & semantics",
    "SD": "Design & duplication",
    "DP": "Design & duplication",
    "PY": "Error handling",
}

# Section display order — first appearance of each title in this list wins.
_SECTION_ORDER = [
    "Structure",
    "Naming",
    "Comments & docstrings",
    "Subscripts & types",
    "Expressions & semantics",
    "Design & duplication",
    "Error handling",
]

_PREAMBLE = """\
You are writing Python that must pass `clean-code check` on the first
attempt. Follow every line below *while writing*, not after — it is cheaper
to write it clean than to fix it in a review pass.
"""

_FOOTER = """\
When you're done, run `clean-code check <paths>` and apply every `fix:` it
prints. If a violation isn't obvious, run `clean-code explain <RULE_ID>` for
a before/after example.
"""


def build_guide(config: "Config") -> str:
    """Render the enabled rule set as a generation-time briefing."""
    sections: dict[str, list[str]] = {title: [] for title in _SECTION_ORDER}
    for rule in _enabled_rules(config):
        bullet = _bullet(rule, config)
        if bullet is not None:
            sections[_section_title(rule.id)].append(bullet)

    blocks = [_PREAMBLE]
    for title in _SECTION_ORDER:
        bullets = sections[title]
        if not bullets:
            continue
        blocks.append(f"## {title}\n" + "\n".join(bullets) + "\n")
    blocks.append(_FOOTER)
    return "\n".join(blocks)


def build_agents_md(config: "Config") -> str:
    """The same briefing, wrapped for pasting into a project's CLAUDE.md/AGENTS.md."""
    lines = [
        "## Python style (enforced by clean-code)",
        "",
        "- Follow the brief below while writing Python in this repo.",
        "- Run `clean-code check` on changed files before finishing.",
        "- Fix every `fix:` clean-code prints; never suppress a violation.",
        "",
        "",
    ]
    return "\n".join(lines) + build_guide(config)


def _enabled_rules(config: "Config") -> list["type[Rule] | type[ProjectRule]"]:
    from cleancode.rules import ALL_RULES

    return [rule for rule in ALL_RULES if config.rules[rule.id].enabled]


def _section_title(rule_id: str) -> str:
    return _BAND_TITLES[rule_id[:2]]


def _bullet(rule: "type[Rule] | type[ProjectRule]", config: "Config") -> str | None:
    if rule.guidance is None:
        return None
    options = config.rules[rule.id].options
    return f"- {rule.guidance.format(**options)}"
