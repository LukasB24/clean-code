"""Engine-level tests: suppressions, syntax errors, registry sanity."""

import re

from cleancode.config import Config
from cleancode.rules import ALL_RULES, RULES_BY_ID


class TestSuppressions:
    def test_targeted_disable_suppresses_only_that_rule(self, analyze):
        source = "tmp = 1  # cleancode: disable=NM202\n"
        assert analyze(source).violations == []

    def test_blanket_disable_suppresses_everything_on_the_line(self, analyze):
        source = "d = tmp2  # cleancode: disable\ntmp = d\n"
        remaining = analyze(source).violations
        assert [violation.line for violation in remaining] == [2]

    def test_disable_of_other_rule_does_not_suppress(self, analyze):
        source = "tmp = 1  # cleancode: disable=ST101\n"
        assert [violation.rule_id for violation in analyze(source).violations] == ["NM202"]

    def test_no_suppress_flag_reports_anyway(self, analyze):
        source = "tmp = 1  # cleancode: disable\n"
        config = Config.default()
        config.honor_suppressions = False
        result = analyze(source, config=config)
        assert [violation.rule_id for violation in result.violations] == ["NM202"]


class TestParseErrors:
    def test_syntax_error_is_reported_not_raised(self, analyze):
        result = analyze("def broken(:\n    pass\n")
        assert result.parse_error is not None
        assert not result.ok
        assert result.violations == []


class TestRegistry:
    def test_rule_ids_are_unique_and_well_formed(self):
        ids = [rule.id for rule in ALL_RULES]
        assert len(ids) == len(set(ids))
        assert all(re.fullmatch(r"(ST|NM|CM|SL|TY|SM|DP|SD)\d{3}", rule_id) for rule_id in ids)
        assert RULES_BY_ID.keys() == set(ids)

    def test_every_rule_has_the_required_metadata(self):
        for rule in ALL_RULES:
            assert rule.name and rule.description
            assert isinstance(rule.default_options, dict)


class TestOrdering:
    def test_violations_are_sorted_by_position(self, analyze):
        source = "tmp = 1\nd = 2\n"
        lines = [violation.line for violation in analyze(source).violations]
        assert lines == sorted(lines)
