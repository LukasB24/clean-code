"""Self-check for run_adversarial_loop.py — no network calls, no real claude/clean-code."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import run_adversarial_loop as loop


def _fake_run(result_text: str, returncode: int = 0):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, returncode, stdout=json.dumps({"result": result_text, "is_error": False}), stderr=""
        )

    return _run


def test_call_claude_parses_result(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("hello"))
    invocation = loop.ClaudeInvocation(model="sonnet")
    assert loop.call_claude("sys", "user", invocation) == "hello"


def test_call_claude_raises_on_error_payload(monkeypatch):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"result": "", "is_error": True}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
    try:
        loop.call_claude("sys", "user", loop.ClaudeInvocation(model="sonnet"))
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


def test_call_claude_passes_permission_mode_flag(monkeypatch):
    seen_commands = []

    def _run(cmd, **kwargs):
        seen_commands.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"result": "ok", "is_error": False}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
    invocation = loop.ClaudeInvocation(model="sonnet", tools="Read", permission_mode="plan")
    loop.call_claude("sys", "user", invocation)
    assert "--permission-mode" in seen_commands[0]
    assert "plan" in seen_commands[0]


def test_generate_code_strips_markdown_fence(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run("```python\nx = 1\n```"))
    assert loop.generate_code("a domain", "sonnet") == "x = 1"


def test_run_linter_captures_stdout(monkeypatch):
    def _run(cmd, **kwargs):
        assert cmd[0] == "clean-code"
        return subprocess.CompletedProcess(cmd, 1, stdout="1:0: warning NM202 ...\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    lint_report = loop.run_linter("x = 1")
    assert "NM202" in lint_report


def test_run_linter_real_pass_if_installed():
    if shutil.which("clean-code") is None:
        return
    lint_report = loop.run_linter("def f():\n    return 1\n")
    assert "clean" in lint_report or "violation" in lint_report


def test_build_todo_section_contains_all_parts():
    section = loop.build_todo_section("a domain", "code_here", "### TODO: New AST Rule - X")
    assert "a domain" in section
    assert "### TODO: New AST Rule - X" in section
    assert "code_here" in section


def test_append_todo_writes_section(tmp_path):
    todo_path = tmp_path / "todo.md"
    todo_path.write_text("# Road map\n")
    loop.append_todo(todo_path, "\n## new finding\n")
    assert "## new finding" in todo_path.read_text()


def test_highest_semantic_rule_id_scans_rule_files(tmp_path):
    rules_dir = tmp_path / "cleancode" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "semantic.py").write_text('id = "SM611"\nid = "SM613"\n')
    (rules_dir / "structure.py").write_text('id = "ST101"\n')
    expected_highest_id = 613
    assert loop._highest_semantic_rule_id(tmp_path) == expected_highest_id


def test_highest_semantic_rule_id_defaults_when_none_found(tmp_path):
    rules_dir = tmp_path / "cleancode" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "structure.py").write_text('id = "ST101"\n')
    default_highest_id = 611
    assert loop._highest_semantic_rule_id(tmp_path) == default_highest_id


def test_plan_rule_forces_read_only_tools(monkeypatch):
    seen_commands = []

    def _run(cmd, **kwargs):
        seen_commands.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"result": "plan text", "is_error": False}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
    invocation = loop.ClaudeInvocation(model="sonnet", tools="Read Write Edit")
    plan_text = loop.plan_rule("some finding", 612, invocation)
    assert plan_text == "plan text"
    command = seen_commands[0]
    assert command[command.index("--tools") + 1] == "Read Grep Glob"
    assert command[command.index("--permission-mode") + 1] == "plan"
    # the caller's broader tools list must not leak into the read-only planner call
    assert invocation.tools == "Read Write Edit"


def test_implement_rule_forces_edit_tools(monkeypatch):
    seen_commands = []

    def _run(cmd, **kwargs):
        seen_commands.append(cmd)
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"result": "done", "is_error": False}), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", _run)
    loop.implement_rule("a plan", loop.ClaudeInvocation(model="sonnet"))
    command = seen_commands[0]
    assert command[command.index("--tools") + 1] == "Read Write Edit"
    assert command[command.index("--permission-mode") + 1] == "acceptEdits"


def test_create_worktree_issues_git_worktree_add(monkeypatch):
    seen_commands = []

    def _run(cmd, **kwargs):
        seen_commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    loop.create_worktree("adversarial/test-branch")
    assert seen_commands[0][:3] == ["git", "worktree", "add"]
    assert "adversarial/test-branch" in seen_commands[0]


def test_remove_worktree_deletes_branch_when_discarding(monkeypatch):
    seen_commands = []

    def _run(cmd, **kwargs):
        seen_commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    target = loop.IterationBranch(worktree=Path("/tmp/fake"), branch="adversarial/test-branch")
    loop.remove_worktree(target, keep_branch=False)
    assert seen_commands[0][:3] == ["git", "worktree", "remove"]
    assert seen_commands[1][:2] == ["git", "branch"]


def test_remove_worktree_keeps_branch_when_requested(monkeypatch):
    seen_commands = []
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: seen_commands.append(cmd) or subprocess.CompletedProcess(cmd, 0)
    )
    target = loop.IterationBranch(worktree=Path("/tmp/fake"), branch="adversarial/x")
    loop.remove_worktree(target, keep_branch=True)
    assert len(seen_commands) == 1
    assert seen_commands[0][:3] == ["git", "worktree", "remove"]


def test_verify_worktree_fails_when_pytest_fails(monkeypatch, tmp_path):
    def _run(cmd, **kwargs):
        if "pytest" in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout="1 failed", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    target = loop.IterationBranch(worktree=tmp_path, branch="adversarial/x")
    passed, message = loop.verify_worktree(target, "x = 1", "")
    assert not passed
    assert "pytest failed" in message


def test_verify_worktree_fails_when_no_new_rule_fires(monkeypatch, tmp_path):
    def _run(cmd, **kwargs):
        if "pytest" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="1:0: warning SM611 ...\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    target = loop.IterationBranch(worktree=tmp_path, branch="adversarial/x")
    passed, message = loop.verify_worktree(target, "x = 1", "1:0: warning SM611 ...\n")
    assert not passed
    assert "no new rule fired" in message


def test_verify_worktree_passes_when_new_rule_fires(monkeypatch, tmp_path):
    def _run(cmd, **kwargs):
        if "pytest" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="1:0: warning SM612 ...\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    target = loop.IterationBranch(worktree=tmp_path, branch="adversarial/x")
    passed, _ = loop.verify_worktree(target, "x = 1", "")
    assert passed


def test_finalize_pr_issues_expected_command_sequence(monkeypatch, tmp_path):
    seen_commands = []

    def _run(cmd, **kwargs):
        seen_commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/x/y/pull/1\n", stderr="")

    monkeypatch.setattr(subprocess, "run", _run)
    target = loop.IterationBranch(worktree=tmp_path, branch="adversarial/x")
    pr_url = loop.finalize_pr(target, "title", "body")

    assert pr_url == "https://github.com/x/y/pull/1"
    git_commands = [(cmd[1], cmd[3]) for cmd in seen_commands[:3]]
    assert git_commands == [("-C", "add"), ("-C", "commit"), ("-C", "push")]
    assert seen_commands[3][:3] == ["gh", "pr", "create"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
