"""The generate → check → refine loop."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Callable, Literal

from cleancode.config import Config
from cleancode.engine import analyze_source
from cleancode.llm.client import LLMClient
from cleancode.llm.prompts import build_system_prompt, render_feedback
from cleancode.models import CheckResult, Severity, Violation

_CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
_SUPPRESSION_COMMENT = re.compile(r"#.*cleancode:\s*disable")

StopReason = Literal["clean", "max_iterations", "no_improvement"]
Phase = Literal["generating", "checking", "checked", "refining"]


@dataclass
class ProgressEvent:
    """A step the feedback loop is about to take or has just finished.

    Emitted through the ``on_progress`` callback so callers (the CLI) can show
    live status instead of a silent wait while the model responds.
    """

    phase: Phase
    iteration: int
    message: str


ProgressCallback = Callable[[ProgressEvent], None]


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


def generate_clean_code(  # cleancode: disable=ST104
    task: str,
    client: LLMClient,
    config: Config | None = None,
    max_iterations: int = 3,
    on_progress: ProgressCallback | None = None,
) -> GenerationResult:
    """Ask ``client`` to solve ``task``, re-prompting with violations until clean.

    Runs at most ``max_iterations`` refinement rounds after the initial
    generation. Always returns the best attempt seen, never a later-but-worse one.
    ``on_progress`` receives a :class:`ProgressEvent` before each model call and
    after each analysis, so a caller can narrate the otherwise silent wait.
    """
    if config is None:
        config = Config.default()
    notify = on_progress or _ignore_progress

    system = build_system_prompt(config)
    messages: list[dict[str, str]] = [{"role": "user", "content": task}]
    iterations: list[Iteration] = []
    stop_reason: StopReason = "max_iterations"

    for iteration_index in range(max_iterations + 1):
        notify(ProgressEvent("generating", iteration_index, "asking the model for code"))
        reply = client.complete(system=system, messages=messages)
        notify(ProgressEvent("checking", iteration_index, "analyzing the generated code"))
        code = _extract_code(reply)
        check_result = _check_generated(code, config)
        iterations.append(Iteration(code=code, check_result=check_result))
        notify(ProgressEvent("checked", iteration_index, _summarize(check_result)))

        if check_result.ok:
            stop_reason = "clean"
            break
        if _stalled(iterations):
            stop_reason = "no_improvement"
            break
        notify(ProgressEvent("refining", iteration_index, "sending the violations back"))
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": render_feedback(check_result, code)})

    best = min(iterations, key=lambda iteration: _badness(iteration.check_result))
    return GenerationResult(
        code=best.code,
        clean=best.check_result.ok,
        stop_reason=stop_reason,
        iterations=iterations,
    )


def _ignore_progress(event: ProgressEvent) -> None:
    """Default no-op sink when the caller supplies no progress callback."""


def _summarize(check_result: CheckResult) -> str:
    """One-line human summary of a check result for progress output."""
    if check_result.parse_error:
        return f"generated code did not parse ({check_result.parse_error})"
    count = len(check_result.violations)
    if count == 0:
        return "clean"
    return f"{count} violation(s)"


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
