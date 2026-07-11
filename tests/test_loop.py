"""LLM feedback loop tests. Everything runs offline against a scripted fake."""

import pytest

from cleancode.config import Config
from cleancode.engine import analyze_source
from cleancode.llm import build_system_prompt, generate_clean_code, render_feedback

CLEAN_REPLY = "```python\ndef double_prices(prices):\n    return [price * 2 for price in prices]\n```"
DIRTY_REPLY = "```python\ndef process_data(data):\n    tmp = [entry for entry in data]\n    return tmp\n```"
LESS_DIRTY_REPLY = "```python\ndef copy_rows(rows):\n    tmp = [row for row in rows]\n    return tmp\n```"
BROKEN_REPLY = "```python\ndef broken(:\n    pass\n```"
SUPPRESSING_REPLY = "```python\ndef copy_rows(rows):\n    tmp = list(rows)  # cleancode: disable=NM202\n    return tmp\n```"


class FakeLLMClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, *, system, messages):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages]})
        return self.replies.pop(0)


class TestLoop:
    def test_stops_immediately_when_first_attempt_is_clean(self):
        client = FakeLLMClient([CLEAN_REPLY])
        result = generate_clean_code("double the prices", client)
        assert result.clean and result.stop_reason == "clean"
        assert len(result.iterations) == 1
        assert "double_prices" in result.code

    def test_feeds_violations_back_and_converges(self):
        client = FakeLLMClient([DIRTY_REPLY, CLEAN_REPLY])
        result = generate_clean_code("copy the data", client)
        assert result.clean and result.stop_reason == "clean"
        feedback = client.calls[1]["messages"][-1]["content"]
        assert "NM202" in feedback and "Fix" in feedback

    def test_stops_on_no_improvement_and_returns_best(self):
        client = FakeLLMClient([LESS_DIRTY_REPLY, DIRTY_REPLY])
        result = generate_clean_code("copy the data", client, max_iterations=3)
        assert result.stop_reason == "no_improvement"
        assert not result.clean
        assert "copy_rows" in result.code  # best attempt, not the newest

    def test_max_iterations_is_respected(self):
        client = FakeLLMClient([DIRTY_REPLY, LESS_DIRTY_REPLY, CLEAN_REPLY])
        result = generate_clean_code("copy the data", client, max_iterations=1)
        assert len(result.iterations) == 2
        assert result.stop_reason == "max_iterations"

    def test_syntax_error_becomes_feedback(self):
        client = FakeLLMClient([BROKEN_REPLY, CLEAN_REPLY])
        result = generate_clean_code("anything", client)
        assert result.clean
        feedback = client.calls[1]["messages"][-1]["content"]
        assert "does not parse" in feedback

    def test_suppression_comments_in_generated_code_are_violations(self):
        client = FakeLLMClient([SUPPRESSING_REPLY, CLEAN_REPLY])
        result = generate_clean_code("copy the rows", client)
        assert result.clean
        first_check = result.iterations[0].check_result
        assert any(v.rule_id == "GEN001" for v in first_check.violations)

    def test_plain_code_reply_without_fences_is_accepted(self):
        client = FakeLLMClient(["def add_two(number):\n    return number + 2\n"])
        result = generate_clean_code("add two", client)
        assert result.clean


class TestProgress:
    def test_reports_generating_before_the_model_call(self):
        events = []
        order = []

        class RecordingClient:
            def complete(self, *, system, messages):
                order.append("model-called")
                return CLEAN_REPLY

        def record(event):
            order.append(f"progress:{event.phase}")
            events.append(event)

        generate_clean_code("double", RecordingClient(), on_progress=record)

        # the 'generating' event must reach the caller before the blocking call
        assert order[0] == "progress:generating"
        assert order[1] == "model-called"
        phases = [event.phase for event in events]
        assert phases == ["generating", "checking", "checked"]
        assert events[-1].message == "clean"

    def test_emits_refining_between_iterations(self):
        client = FakeLLMClient([DIRTY_REPLY, CLEAN_REPLY])
        events = []
        generate_clean_code("copy the data", client, on_progress=events.append)
        phases = [event.phase for event in events]
        assert phases == [
            "generating", "checking", "checked", "refining",
            "generating", "checking", "checked",
        ]
        assert [event.iteration for event in events[:4]] == [0, 0, 0, 0]
        assert events[4].iteration == 1

    def test_progress_is_optional(self):
        # no callback -> no error, loop behaves exactly as before
        result = generate_clean_code("double", FakeLLMClient([CLEAN_REPLY]))
        assert result.clean


class TestPrompts:
    def test_system_prompt_lists_enabled_rules_only(self):
        config = Config.default()
        config.rules["SL401"].enabled = False
        system = build_system_prompt(config)
        assert "ST101" in system and "SL401" not in system

    def test_feedback_quotes_the_offending_line(self):
        code = "tmp = 1\n"
        result = analyze_source(code)
        feedback = render_feedback(result, code)
        assert "> tmp = 1" in feedback
        assert "NM202" in feedback


class TestClaudeCodeClient:
    def test_missing_cli_raises_helpful_error(self, monkeypatch):
        import cleancode.llm.claude_code_client as module

        monkeypatch.setattr(module.shutil, "which", lambda binary: None)
        with pytest.raises(module.ClaudeCodeError, match="not found on PATH"):
            module.ClaudeCodeClient()

    def test_complete_invokes_cli_and_returns_stdout(self, monkeypatch):
        import cleancode.llm.claude_code_client as module

        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["input"] = kwargs["input"]
            return type("Completed", (), {"stdout": "  hello  ", "stderr": ""})()

        monkeypatch.setattr(module.shutil, "which", lambda binary: "/usr/bin/claude")
        monkeypatch.setattr(module.subprocess, "run", fake_run)

        client = module.ClaudeCodeClient(model="claude-sonnet-5")
        reply = client.complete(
            system="sys",
            messages=[
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "prior"},
                {"role": "user", "content": "again"},
            ],
        )
        assert reply == "hello"
        assert captured["command"][:2] == ["claude", "--print"]
        assert "--append-system-prompt" in captured["command"]
        assert "--model" in captured["command"]
        # multi-turn history is flattened with role labels, latest turn last
        assert captured["input"].strip().endswith("User:\nagain")

    def test_single_message_is_passed_verbatim(self, monkeypatch):
        import cleancode.llm.claude_code_client as module

        captured = {}

        def fake_run(command, **kwargs):
            captured["input"] = kwargs["input"]
            return type("Completed", (), {"stdout": "ok", "stderr": ""})()

        monkeypatch.setattr(module.shutil, "which", lambda binary: "/usr/bin/claude")
        monkeypatch.setattr(module.subprocess, "run", fake_run)

        module.ClaudeCodeClient().complete(
            system="sys", messages=[{"role": "user", "content": "just this"}]
        )
        assert captured["input"] == "just this"

    def test_nonzero_exit_becomes_claude_code_error(self, monkeypatch):
        import subprocess

        import cleancode.llm.claude_code_client as module

        def fake_run(command, **kwargs):
            raise subprocess.CalledProcessError(2, command, stderr="boom")

        monkeypatch.setattr(module.shutil, "which", lambda binary: "/usr/bin/claude")
        monkeypatch.setattr(module.subprocess, "run", fake_run)

        with pytest.raises(module.ClaudeCodeError, match="boom"):
            module.ClaudeCodeClient().complete(
                system="s", messages=[{"role": "user", "content": "x"}]
            )

    def test_client_satisfies_loop(self, monkeypatch):
        """A ClaudeCodeClient drops into generate_clean_code unchanged."""
        import cleancode.llm.claude_code_client as module

        def fake_run(command, **kwargs):
            return type("Completed", (), {"stdout": CLEAN_REPLY, "stderr": ""})()

        monkeypatch.setattr(module.shutil, "which", lambda binary: "/usr/bin/claude")
        monkeypatch.setattr(module.subprocess, "run", fake_run)

        result = generate_clean_code("double the prices", module.ClaudeCodeClient())
        assert result.clean and result.stop_reason == "clean"


class TestAnthropicClient:
    def test_missing_dependency_raises_helpful_error(self, monkeypatch):
        import builtins

        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked)
        from cleancode.llm.anthropic_client import AnthropicClient

        with pytest.raises(ImportError, match="cleancode\\[llm\\]"):
            AnthropicClient()

    def test_request_assembly(self, monkeypatch):
        anthropic = pytest.importorskip("anthropic")

        captured = {}

        class FakeBlock:
            type = "text"
            text = "hello"

        class FakeMessages:
            def create(self, **kwargs):
                captured.update(kwargs)
                return type("Response", (), {"content": [FakeBlock()]})()

        class FakeAnthropic:
            def __init__(self, **kwargs):
                self.messages = FakeMessages()

        monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)
        from cleancode.llm.anthropic_client import AnthropicClient

        client = AnthropicClient(model="claude-sonnet-5")
        reply = client.complete(
            system="sys", messages=[{"role": "user", "content": "hi"}]
        )
        assert reply == "hello"
        assert captured["model"] == "claude-sonnet-5"
        assert captured["system"] == "sys"
        assert "temperature" not in captured
