"""Engine-level tests: suppressions, syntax errors, file walking, registry sanity."""

import re

from cleancode.config import Config
from cleancode.engine import analyze_paths
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

    def test_non_utf8_file_is_reported_not_raised(self, tmp_path):
        # regression: one undecodable file used to abort the whole run
        bad = tmp_path / "latin1.py"
        bad.write_bytes("x = 'caf\xe9'\n".encode("latin-1"))
        (tmp_path / "fine.py").write_text("VALUE = 1\n", encoding="utf-8")
        results = analyze_paths([tmp_path])
        by_name = {result.path.rsplit("/", 1)[-1]: result for result in results}
        assert "not valid UTF-8" in by_name["latin1.py"].parse_error
        assert by_name["fine.py"].ok


class TestExcludes:
    def test_relative_pattern_matches_below_the_project_root(self, tmp_path):
        # regression: the documented `exclude = ["migrations/**"]` example
        # never matched because patterns were only tried against absolute paths
        (tmp_path / "pyproject.toml").write_text(
            '[tool.cleancode]\nexclude = ["migrations/**"]\n', encoding="utf-8"
        )
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "auto.py").write_text("tmp = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        config = Config.load(tmp_path)
        results = analyze_paths([tmp_path], config)
        assert [result.path.rsplit("/", 1)[-1] for result in results] == ["app.py"]

    def test_absolute_style_default_excludes_still_match(self, tmp_path):
        venv = tmp_path / "venv"
        venv.mkdir()
        (venv / "vendored.py").write_text("tmp = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
        results = analyze_paths([tmp_path])
        assert [result.path.rsplit("/", 1)[-1] for result in results] == ["app.py"]


class TestRegistry:
    def test_rule_ids_are_unique_and_well_formed(self):
        ids = [rule.id for rule in ALL_RULES]
        assert len(ids) == len(set(ids))
        assert all(re.fullmatch(r"(ST|NM|CM|SL|TY|SM|DP|SD|PY)\d{3}", rule_id) for rule_id in ids)
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
