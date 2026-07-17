"""Self-test for the `clean-code explain` example registry.

Every rule's BAD snippet must actually trigger it and its GOOD snippet must
not — this is a permanent regression net: a future rule change that stops
firing on its own BAD example fails here.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from cleancode.config import Config
from cleancode.engine import analyze_paths, analyze_source
from cleancode.examples import EXAMPLES
from cleancode.models import Violation
from cleancode.rules import ALL_RULES, RULES_BY_ID
from cleancode.rules.base import ProjectRule


def _single_rule_config(rule_id: str) -> Config:
    config = Config.default()
    for other_id, rule_config in config.rules.items():
        rule_config.enabled = other_id == rule_id
    return config


def _violations_for(rule_id: str, source: str, tmp_path: Path) -> list[Violation]:
    """Run only ``rule_id`` over ``source``, routing project rules through a real file."""
    config = _single_rule_config(rule_id)
    if issubclass(RULES_BY_ID[rule_id], ProjectRule):
        file_path = tmp_path / "example.py"
        file_path.write_text(textwrap.dedent(source), encoding="utf-8")
        results = analyze_paths([file_path], config)
        return [violation for result in results for violation in result.violations]
    return analyze_source(textwrap.dedent(source), config).violations


class TestExampleCoverage:
    def test_every_rule_has_an_example(self):
        assert EXAMPLES.keys() == {rule.id for rule in ALL_RULES}


class TestExampleBehavior:
    @pytest.mark.parametrize("rule_id", sorted(EXAMPLES))
    def test_bad_triggers_the_rule(self, rule_id: str, tmp_path: Path):
        violations = _violations_for(rule_id, EXAMPLES[rule_id].bad, tmp_path)
        assert any(violation.rule_id == rule_id for violation in violations), (
            f"{rule_id}'s BAD example didn't trigger it"
        )

    @pytest.mark.parametrize("rule_id", sorted(EXAMPLES))
    def test_good_does_not_trigger_the_rule(self, rule_id: str, tmp_path: Path):
        violations = _violations_for(rule_id, EXAMPLES[rule_id].good, tmp_path)
        assert not any(violation.rule_id == rule_id for violation in violations), (
            f"{rule_id}'s GOOD example triggered it"
        )
