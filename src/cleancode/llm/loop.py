"""The generate → check → refine loop."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Literal

from cleancode.config import Config
from cleancode.engine import analyze_source
from cleancode.llm.client import LLMClient
from cleancode.llm.prompts import build_system_prompt, render_feedback
from cleancode.models import CheckResult, Severity, Violation

_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
_SUPPRESSION_COMMENT = re.compile(r"#.*cleancode:\s*disable")

StopReason = Literal["clean", "max_iterations", "no_improvement"]


@dataclass
class Iteration:
    code: str
    check_result: CheckResult


@dataclass
class GenerationResult:
    code: str
    clean: bool
    stop_reason: StopReason
    iterations: list[Iteration] = field(default_factory=list)


def generate_clean_code(
    task: str,
    client: LLMClient,
    config: Config | None = None,
    max_iterations: int = 3,
) -> GenerationResult:
    """Ask ``client`` to solve ``task``, re-prompting with violations until clean.

    Runs at most ``max_iterations`` refinement rounds after the initial
    generation. Always returns the best attempt seen, never a later-but-worse one.
    """
    if config is None:
        config = Config.default()

    system = build_system_prompt(config)
    messages: list[dict[str, str]] = [{"role": "user", "content": task}]
    iterations: list[Iteration] = []
    stop_reason: StopReason = "max_iterations"

    for _ in range(max_iterations + 1):
        reply = client.complete(system=system, messages=messages)
        code = _extract_code(reply)
        check_result = _check_generated(code, config)
        iterations.append(Iteration(code=code, check_result=check_result))

        if check_result.ok:
            stop_reason = "clean"
            break
        if _stalled(iterations):
            stop_reason = "no_improvement"
            break
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": render_feedback(check_result, code)})

    best = min(iterations, key=lambda iteration: _badness(iteration.check_result))
    return GenerationResult(
        code=best.code,
        clean=best.check_result.ok,
        stop_reason=stop_reason,
        iterations=iterations,
    )


def _extract_code(reply: str) -> str:
    """The last fenced python block; falls back to the raw reply if it parses."""
    blocks = _CODE_BLOCK.findall(reply)
    if blocks:
        return blocks[-1].strip("\n")
    try:
        ast.parse(reply)
    except SyntaxError:
        return reply  # let the analyzer produce the parse error as feedback
    return reply


def _check_generated(code: str, config: Config) -> CheckResult:
    """Analyze with suppressions ignored; suppression comments are violations."""
    check_result = analyze_source(code, config, honor_suppressions=False)
    if check_result.parse_error:
        return check_result
    for line_number, line in enumerate(code.splitlines(), start=1):
        if _SUPPRESSION_COMMENT.search(line):
            check_result.violations.append(
                Violation(
                    rule_id="GEN001",
                    rule_name="no-suppression-comments",
                    message="generated code must not silence the checker with "
                    "`# cleancode: disable`",
                    line=line_number,
                    col=0,
                    severity=Severity.ERROR,
                    suggestion="remove the suppression comment and fix the underlying issue",
                )
            )
    check_result.violations.sort(key=lambda violation: (violation.line, violation.col))
    return check_result


def _badness(check_result: CheckResult) -> tuple[int, int]:
    """Orderable badness: parse errors are worst, then error-weighted counts."""
    if check_result.parse_error:
        return (1, 10**6)
    weight = sum(
        3 if violation.severity == Severity.ERROR else 1
        for violation in check_result.violations
    )
    return (0, weight)


def _stalled(iterations: list[Iteration]) -> bool:
    """True when the newest attempt is no better than everything before it."""
    if len(iterations) < 2:
        return False
    newest = _badness(iterations[-1].check_result)
    best_before = min(_badness(iteration.check_result) for iteration in iterations[:-1])
    return newest >= best_before
