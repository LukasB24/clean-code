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
        result = runner.invoke(main, ["check", str(path)])
        assert result.exit_code == 1
        assert "NM202" in result.output

    def test_json_output_is_valid_and_structured(self, runner, tmp_path):
        path = write(tmp_path, "dirty.py", DIRTY)
        result = runner.invoke(main, ["check", "--json", str(path)])
        payload = json.loads(result.output)
        assert payload[0]["path"] == str(path)
        assert payload[0]["ok"] is False
        first = payload[0]["violations"][0]
        assert {"rule_id", "message", "line", "col", "severity", "suggestion"} <= first.keys()

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


CLEAN_GENERATE_REPLY = (
    "```python\ndef add_two_numbers(first, second):\n    return first + second\n```"
)


class _FakeGenerateClient:
    def __init__(self, reply=CLEAN_GENERATE_REPLY):
        self.reply = reply

    def complete(self, *, system, messages):
        return self.reply


class TestGenerate:
    def _patch_client(self, monkeypatch, client):
        import cleancode.cli as cli_module

        monkeypatch.setattr(cli_module, "_build_client", lambda via, model: client)

    def test_prints_progress_to_stderr_and_code_to_stdout(self, runner, monkeypatch):
        self._patch_client(monkeypatch, _FakeGenerateClient())
        result = runner.invoke(main, ["generate", "add two numbers"])
        assert result.exit_code == 0
        assert "def add_two_numbers(first, second):" in result.stdout
        assert "generating clean code for: add two numbers" in result.stderr
        assert "[0]" in result.stderr and "clean" in result.stderr
        # captured (non-TTY) output must degrade to static lines: no spinner
        # carriage returns or ANSI erase codes leaking into logs/pipes
        assert "\r" not in result.stderr and "\x1b[K" not in result.stderr

    def test_writes_to_out_file(self, runner, monkeypatch, tmp_path):
        self._patch_client(monkeypatch, _FakeGenerateClient())
        out = tmp_path / "result.py"
        result = runner.invoke(main, ["generate", "add", "--out", str(out)])
        assert result.exit_code == 0
        assert "def add_two_numbers" in out.read_text()

    def test_negative_max_iterations_is_a_usage_error(self, runner):
        result = runner.invoke(main, ["generate", "x", "--max-iterations=-1"])
        assert result.exit_code == 2

    def test_backend_failure_mid_loop_is_reported_cleanly_not_as_traceback(
        self, runner, monkeypatch
    ):
        # regression test: a ClaudeCodeError (auth conflict, rate limit, ...)
        # raised while the loop is running must not surface as a raw traceback
        from cleancode.llm.claude_code_client import ClaudeCodeError

        class FailingClient:
            def complete(self, *, system, messages):
                raise ClaudeCodeError("claude.ai connectors are disabled because ...")

        self._patch_client(monkeypatch, FailingClient())
        result = runner.invoke(main, ["generate", "make a json parser"])
        assert result.exit_code == 1
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert "generation failed" in result.stderr
        assert "Traceback" not in result.output


class TestRules:
    def test_lists_all_rules(self, runner):
        result = runner.invoke(main, ["rules"])
        assert result.exit_code == 0
        for rule_id in ("ST101", "NM201", "CM301", "SL401"):
            assert rule_id in result.output
