"""CLI tests via click's CliRunner."""

import json

import pytest
from click.testing import CliRunner

from cleancode.cli import main

DIRTY = "def process_data(data):\n    tmp = [d for d in data]\n    return tmp\n"
CLEAN = "def double_prices(prices):\n    return [price * 2 for price in prices]\n"


@pytest.fixture
def runner():
    return CliRunner()


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


class TestCheck:
    def test_clean_file_exits_zero(self, runner, tmp_path):
        path = write(tmp_path, "clean.py", CLEAN)
        result = runner.invoke(main, ["check", str(path)])
        assert result.exit_code == 0
        assert "clean" in result.output

    def test_dirty_file_exits_one_and_reports(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", DIRTY)
        result = runner.invoke(main, ["check", "--min-severity", "warning", str(path)])
        assert result.exit_code == 1
        assert "NM202" in result.output

    def test_default_shows_warnings_but_hides_info(self, runner, tmp_path):
        source = "def usr_mgr(data):\n    tmp = [d for d in data]\n    return tmp\n"
        path = write(tmp_path, "dirty.py", source)
        result = runner.invoke(main, ["check", str(path)])
        assert result.exit_code == 1
        assert "NM202" in result.output  # warning: shown by default
        assert "NM203" not in result.output  # info: hidden by default
        assert "hidden below --min-severity warning" in result.output

    def test_json_output_is_valid_and_structured(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", DIRTY)
        result = runner.invoke(
            main, ["check", "--json", "--min-severity", "warning", str(path)]
        )
        payload = json.loads(result.output)
        assert payload[0]["path"] == str(path)
        first = payload[0]["violations"][0]
        assert {"rule_id", "message", "line", "col", "severity", "suggestion"} <= first.keys()

    def test_json_output_respects_min_severity(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", DIRTY)
        result = runner.invoke(
            main, ["check", "--json", "--min-severity", "error", str(path)]
        )
        payload = json.loads(result.output)
        assert payload == []

    def test_json_output_omits_clean_files(self, runner, tmp_path):
        clean_path = write(tmp_path, "clean.py", CLEAN)
        dirty_path = write(tmp_path, "dirty.py", DIRTY)
        result = runner.invoke(
            main, ["check", "--json", "--min-severity", "warning", str(clean_path), str(dirty_path)]
        )
        payload = json.loads(result.output)
        assert [entry["path"] for entry in payload] == [str(dirty_path)]

    def test_syntax_error_exits_two(self, runner, tmp_path):
        path = write(tmp_path, "broken.py", "def broken(:\n")
        result = runner.invoke(main, ["check", str(path)])
        assert result.exit_code == 2
        assert "syntax error" in result.output

    def test_select_runs_only_named_rules(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", DIRTY)
        result = runner.invoke(main, ["check", "--select", "NM201", str(path)])
        assert "NM202" not in result.output

    def test_ignore_skips_named_rules(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", "tmp = 1\n")
        result = runner.invoke(main, ["check", "--ignore", "NM202", str(path)])
        assert result.exit_code == 0

    def test_unknown_select_id_is_a_usage_error(self, runner, tmp_path):
        path = write(tmp_path, "clean.py", CLEAN)
        result = runner.invoke(main, ["check", "--select", "ZZ999", str(path)])
        assert result.exit_code == 2

    def test_no_suppress_reports_suppressed_lines(self, runner, tmp_path):
        path = write(tmp_path, "sneaky.py", "tmp = 1  # cleancode: disable\n")
        quiet = runner.invoke(main, ["check", str(path)])
        loud = runner.invoke(main, ["check", "--no-suppress", str(path)])
        assert quiet.exit_code == 0
        assert loud.exit_code == 1

    def test_fail_on_error_lets_warnings_pass(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", "tmp = 1\n")
        result = runner.invoke(main, ["check", "--fail-on", "error", str(path)])
        assert result.exit_code == 0

    def test_directory_is_recursed(self, runner, tmp_path):
        package = tmp_path / "pkg"
        package.mkdir()
        write(package, "dirty.py", DIRTY)
        result = runner.invoke(main, ["check", str(tmp_path)])
        assert result.exit_code == 1


class TestRules:
    def test_lists_all_rules(self, runner):
        result = runner.invoke(main, ["rules"])
        assert result.exit_code == 0
        for rule_id in ("ST101", "NM201", "CM301", "SL401"):
            assert rule_id in result.output
