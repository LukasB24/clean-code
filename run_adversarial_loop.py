#!/usr/bin/env python3
"""Adversarial static-analysis loop.

A Generator role asks Claude Code to write realistic domain code that hides a
deep structural/memory flaw behind clean-looking, low-complexity Python. The
real `clean-code` linter runs against it. A Critic role compares the source to
what the linter caught, and any smell the linter missed becomes a todo.md
entry.

From there, each iteration gets its own throwaway `git worktree` branched from
`main`: a Planner role (read-only tools) drafts an implementation plan for the
missing rule(s), an Implementer role (file-edit tools only, no git/Bash) writes
the new Rule subclass(es), and the orchestrator itself (not an LLM) verifies
the rule actually fires on the fixture before committing, pushing, and opening
a PR via `gh pr create` for manual review.

Requires `claude`, `clean-code` (`pip install -e .`), `git`, and `gh`
(authenticated) all on PATH.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
MAX_REPAIR_ATTEMPTS = 2

logging.basicConfig(
    filename=str(REPO_ROOT / "adversarial_loop.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class ClaudeInvocation:
    model: str
    working_dir: Path | None = None
    tools: str = ""
    permission_mode: str | None = None


@dataclass
class IterationBranch:
    worktree: Path
    branch: str
    code: str
    baseline_output: str


DOMAINS = [
    "a PyTorch training / data-loading pipeline",
    "a FastAPI background-task or request-handling module",
    "a Pandas ETL / data-wrangling workflow",
]

GENERATOR_SYSTEM_PROMPT = """\
You write adversarial fixtures for a Python code-quality linter's test suite.

Write a single, realistic, domain-specific Python module for the domain you
are given. Requirements:
- Looks clean: short functions, low cyclomatic complexity, descriptive names,
  passes basic style/syntax checks.
- Hides at least one deep structural or memory/architectural flaw that a
  naive AST or style linter would not catch — e.g. unbounded eager loading
  into memory, hidden shared mutable state, resource/tensor/connection leaks,
  blocking I/O on an async path, N+1 query patterns, premature device
  placement before multiprocessing forks, redundant runtime checks already
  guaranteed by static types.
- The flaw must be subtle and architectural, not a syntax error, not a typo,
  not something a formatter or basic type checker would flag.

Output ONLY the raw Python source code. No markdown fences, no commentary,
no explanation before or after.
"""

CRITIC_SYSTEM_PROMPT = """\
You audit a Python linter's blind spots. You are given a source file and the
linter's own output for that file. Some smells in the source were caught by
the linter (listed in its output) — ignore those. Find the smells that were
NOT caught: deep structural, architectural, or memory/resource flaws the
linter's checks are blind to.

For each missed smell, output a block in EXACTLY this Markdown template
(repeat the block once per finding, nothing else in your response):

### TODO: New AST Rule - [Rule Name]
- **Description:** [Brief explanation of the hidden smell]
- **Target Node Type:** [e.g., ast.Call, ast.ClassDef]
- **AST Traversal Logic for Agent:** 1. [Step-by-step instructions on how the AST visitor should traverse nodes]
  2. [Condition to trigger the violation]

If the linter already caught everything meaningful, output nothing.
"""

PLANNER_SYSTEM_PROMPT = """\
You are a senior maintainer of a Python AST-based linter (the "clean-code" tool).
You are given one finding from an adversarial-testing loop: a missed code smell,
described with a target AST node type and traversal logic.

Investigate this repository (read-only) to understand the existing pattern:
- src/cleancode/rules/base.py for the Rule base class contract
- src/cleancode/rules/semantic.py for existing SM6xx rule implementations
- src/cleancode/rules/__init__.py for how rules are registered in ALL_RULES
- README.md for the rule documentation table format

Output a concise implementation plan (no code) covering:
- The exact rule id(s) and name(s) to use, starting at the ID given to you
  below — use that number even if the files on disk show a lower existing
  maximum (other iterations of this run may have allocated IDs you can't see
  yet in this checkout).
- Which file(s) need to change.
- One paragraph of plain-English `check()` logic per new rule.
- What README updates are needed (table row + prose clause).
"""

IMPLEMENTER_SYSTEM_PROMPT = """\
You are a senior maintainer of a Python AST-based linter (the "clean-code" tool).
Your current working directory already IS the repository root. Reference every
file as a plain relative path (e.g. `src/cleancode/rules/semantic.py`) — never
invent or prefix an absolute root like `/repo/...`; no such path exists.

You are given an implementation plan for one or more new lint rules. Implement
it exactly:
- Add each new Rule subclass to src/cleancode/rules/semantic.py, following the
  existing pattern in that file (see e.g. RedundantIsinstanceCheck) — class
  attrs id/name/default_severity/default_options/description, and a
  check(self, ctx: FileContext) -> Iterable[Violation] method that walks
  ctx.tree and yields self.violation(...) for each hit.
- Register each new class in src/cleancode/rules/__init__.py: add it to the
  `from cleancode.rules.semantic import (...)` block and to the ALL_RULES list.
- Add a matching row to the rule table in README.md and a matching prose
  clause to the "SM6xx catches structural smells..." paragraph below it.

This repo dogfoods its own linter against its own source — your new code will
be checked by the same rules it implements, so it must itself comply:
- No more than 2 sequential guard-clause returns in one block — extract a
  helper instead of a third.
- No cryptic abbreviations in names (e.g. write `statement`, not `stmt`).
- Keep each function short, shallow, and single-purpose, following the small
  well-named-helper-function style already used elsewhere in semantic.py.
- No magic numbers; no unused imports or variables.

Only edit these files. Do not touch tests, do not run anything, do not use git.
"""


def call_claude(
    system_prompt: str, user_prompt: str, invocation: ClaudeInvocation
) -> str:
    command = [
        "claude",
        "-p",
        "--model",
        invocation.model,
        "--system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--tools",
        invocation.tools,
        "--no-session-persistence",
    ]
    if invocation.permission_mode:
        command += ["--permission-mode", invocation.permission_mode]
    cli_result = subprocess.run(
        command,
        input=user_prompt,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=invocation.working_dir,
    )
    if cli_result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {cli_result.returncode}): {cli_result.stderr}"
        )
    payload = json.loads(cli_result.stdout)
    if payload.get("is_error"):
        raise RuntimeError(f"claude CLI returned an error: {payload}")
    return payload["result"]


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def generate_code(domain: str, model: str) -> str:
    raw = call_claude(
        GENERATOR_SYSTEM_PROMPT, f"Domain: {domain}", ClaudeInvocation(model=model)
    )
    return _strip_code_fence(raw)


def run_linter(code: str) -> str:
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False, dir=tempfile.gettempdir()
    ) as fixture_file:
        fixture_file.write(code)
        tmp_path = Path(fixture_file.name)
    try:
        lint_result = subprocess.run(
            ["clean-code", "check", str(tmp_path), "--min-severity", "info"],
            capture_output=True,
            text=True,
        )
        return lint_result.stdout
    finally:
        tmp_path.unlink(missing_ok=True)


def critique(code: str, linter_output: str, model: str) -> str:
    user_prompt = (
        f"Source file:\n```python\n{code}\n```\n\n"
        f"Linter output for this file:\n```\n{linter_output}\n```"
    )
    return call_claude(
        CRITIC_SYSTEM_PROMPT, user_prompt, ClaudeInvocation(model=model)
    ).strip()


def build_todo_section(domain: str, code: str, critic_md: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"\n## Adversarial finding — {timestamp} ({domain})\n\n"
        f"{critic_md}\n\n"
        f"<details><summary>Fixture code</summary>\n\n"
        f"```python\n{code}\n```\n\n"
        f"</details>\n"
    )


def append_todo(todo_path: Path, section: str) -> None:
    with todo_path.open("a", encoding="utf-8") as handle:
        handle.write(section)


def _highest_semantic_rule_id(src_dir: Path) -> int:
    ids = [
        int(match)
        for path in (src_dir / "cleancode" / "rules").glob("*.py")
        for match in re.findall(r'"SM(\d{3})"', path.read_text())
    ]
    return max(ids, default=611)


def plan_rule(critic_md: str, next_rule_id: int, invocation: ClaudeInvocation) -> str:
    user_prompt = (
        f"Allocate new rule ID(s) starting at SM{next_rule_id}.\n\n"
        f"Finding to address:\n{critic_md}"
    )
    planner_invocation = replace(
        invocation, tools="Read Grep Glob", permission_mode="plan"
    )
    return call_claude(PLANNER_SYSTEM_PROMPT, user_prompt, planner_invocation).strip()


def implement_rule(user_prompt: str, invocation: ClaudeInvocation) -> str:
    implementer_invocation = replace(
        invocation, tools="Read Write Edit", permission_mode="acceptEdits"
    )
    return call_claude(
        IMPLEMENTER_SYSTEM_PROMPT, user_prompt, implementer_invocation
    ).strip()


def build_repair_prompt(plan_md: str, failure_message: str) -> str:
    return (
        "Your previous implementation of this plan failed verification. Do "
        "not start over — read the files you already wrote in this working "
        "directory and fix them.\n\n"
        f"Verification failure:\n{failure_message}\n\n"
        f"Original plan:\n{plan_md}"
    )


def verify_with_repairs(
    target: IterationBranch, plan_md: str, invocation: ClaudeInvocation
) -> tuple[bool, str]:
    passed, message = verify_worktree(target)
    attempt = 0
    while not passed and attempt < MAX_REPAIR_ATTEMPTS:
        attempt += 1
        logger.info(
            f"[repair {attempt}/{MAX_REPAIR_ATTEMPTS}] verification failed, "
            f"asking Claude to fix its own implementation instead of "
            f"restarting the iteration:\n{message}"
        )
        implement_rule(build_repair_prompt(plan_md, message), invocation)
        passed, message = verify_worktree(target)
    return passed, message


def create_worktree(branch: str, code: str, baseline_output: str) -> IterationBranch:
    worktree_path = Path(tempfile.mkdtemp(prefix="adversarial-"))
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch, "main"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return IterationBranch(
        worktree=worktree_path,
        branch=branch,
        code=code,
        baseline_output=baseline_output,
    )


def remove_worktree(target: IterationBranch, keep_branch: bool) -> None:
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target.worktree)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not keep_branch:
        subprocess.run(
            ["git", "branch", "-D", target.branch],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )


def verify_worktree(target: IterationBranch) -> tuple[bool, str]:
    env = {**os.environ, "PYTHONPATH": str(target.worktree / "src")}

    test_result = subprocess.run(
        [sys.executable, "-m", "pytest", str(target.worktree / "tests"), "-q"],
        cwd=target.worktree,
        capture_output=True,
        text=True,
        env=env,
    )
    if test_result.returncode != 0:
        return False, f"pytest failed:\n{test_result.stdout}\n{test_result.stderr}"

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", delete=False
    ) as fixture_file:
        fixture_file.write(target.code)
        fixture_path = Path(fixture_file.name)
    try:
        lint_result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from cleancode.cli import main; main()",
                "check",
                str(fixture_path),
                "--min-severity",
                "info",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        fixture_path.unlink(missing_ok=True)

    new_rule_ids = set(re.findall(r"\b(SM6\d\d)\b", lint_result.stdout))
    old_rule_ids = set(re.findall(r"\b(SM6\d\d)\b", target.baseline_output))
    if not (new_rule_ids - old_rule_ids):
        return False, f"no new rule fired on the fixture:\n{lint_result.stdout}"
    return True, "verified"


def finalize_pr(target: IterationBranch, title: str, body: str) -> str:
    worktree, branch = target.worktree, target.branch
    subprocess.run(["git", "-C", str(worktree), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(worktree), "commit", "-m", title, "-m", body], check=True
    )
    subprocess.run(
        ["git", "-C", str(worktree), "push", "-u", "origin", branch], check=True
    )
    pr_result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=True,
    )
    return pr_result.stdout.strip()


def _diff_summary(worktree: Path) -> str:
    status = subprocess.run(
        ["git", "-C", str(worktree), "status", "--short"],
        capture_output=True,
        text=True,
    )
    diff = subprocess.run(
        ["git", "-C", str(worktree), "diff"], capture_output=True, text=True
    )
    return f"changed files:\n{status.stdout}\ndiff:\n{diff.stdout}"


def run_iteration(model: str, iteration_index: int, next_rule_id: int) -> int:
    domain = random.choice(DOMAINS)
    logger.info(f"[generate] {domain} ...")
    code = generate_code(domain, model)

    logger.info("[lint] running clean-code ...")
    baseline_output = run_linter(code)

    logger.info("[critique] comparing source to linter output ...")
    critic_md = critique(code, baseline_output, model)

    if not critic_md:
        logger.info("[skip] critic found nothing the linter missed")
        return next_rule_id

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    branch = f"adversarial/iter{iteration_index}-{timestamp}"
    logger.info(f"[worktree] creating {branch} from main ...")
    target = create_worktree(branch, code, baseline_output)

    try:
        append_todo(
            target.worktree / "todo.md", build_todo_section(domain, code, critic_md)
        )

        logger.info(
            f"[plan] asking Claude to plan rule(s) starting at SM{next_rule_id} ..."
        )
        invocation = ClaudeInvocation(model=model, working_dir=target.worktree)
        plan_md = plan_rule(critic_md, next_rule_id, invocation)

        logger.info("[implement] asking Claude to implement the plan ...")
        implement_rule(plan_md, invocation)

        logger.info("[verify] running the worktree's own tests + linter ...")
        passed, message = verify_with_repairs(target, plan_md, invocation)
        if not passed:
            logger.warning(f"[fail] verification failed, skipping PR:\n{message}")
            logger.warning(_diff_summary(target.worktree))
            remove_worktree(target, keep_branch=False)
            return next_rule_id

        new_max_id = _highest_semantic_rule_id(target.worktree / "src")
        added = max(new_max_id - (next_rule_id - 1), 1)
        title = f"Add adversarial-loop rule(s) starting at SM{next_rule_id}"
        pr_url = finalize_pr(target, title, plan_md)
        logger.info(f"[done] opened PR: {pr_url}")
        remove_worktree(target, keep_branch=True)
        return next_rule_id + added
    except Exception as error:
        logger.error(f"[fail] iteration errored, skipping PR: {error}")
        remove_worktree(target, keep_branch=False)
        return next_rule_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--model", default="sonnet")
    args = parser.parse_args()

    if shutil.which("clean-code") is None:
        raise SystemExit("clean-code is not on PATH — run `pip install -e .` first.")
    for name in ("claude", "git", "gh"):
        if shutil.which(name) is None:
            raise SystemExit(f"{name} is not on PATH.")

    next_rule_id = _highest_semantic_rule_id(REPO_ROOT / "src") + 1
    for i in range(args.iterations):
        logger.info(f"=== iteration {i + 1}/{args.iterations} ===")
        next_rule_id = run_iteration(args.model, i + 1, next_rule_id)


if __name__ == "__main__":
    main()
