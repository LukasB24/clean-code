"""Analysis engine: parse once, run every enabled rule, apply suppressions."""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import tokenize
from pathlib import Path

from cleancode.config import Config
from cleancode.models import CheckResult, Comment, FileContext

_SUPPRESSION = re.compile(r"cleancode:\s*disable(?:\s*=\s*(?P<ids>[A-Z]{2}\d{3}(?:\s*,\s*[A-Z]{2}\d{3})*))?")


def analyze_source(
    source: str,
    config: Config | None = None,
    path: str = "<string>",
    honor_suppressions: bool = True,
) -> CheckResult:
    """Run all enabled rules over ``source`` and return the sorted violations."""
    from cleancode.rules import ALL_RULES

    if config is None:
        config = Config.default()

    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return CheckResult(path=path, parse_error=f"line {error.lineno}: {error.msg}")

    _attach_parents(tree)
    comments = _extract_comments(source)
    lines = source.splitlines()

    violations = []
    for rule_class in ALL_RULES:
        rule_config = config.rules[rule_class.id]
        if not rule_config.enabled:
            continue
        ctx = FileContext(
            path=path,
            source=source,
            lines=lines,
            tree=tree,
            comments=comments,
            config=rule_config,
        )
        violations.extend(rule_class().check(ctx))

    if honor_suppressions:
        suppressions = _parse_suppressions(comments)
        violations = [
            violation
            for violation in violations
            if not _is_suppressed(violation.line, violation.rule_id, suppressions)
        ]

    violations.sort(key=lambda violation: (violation.line, violation.col, violation.rule_id))
    return CheckResult(path=path, violations=violations)


def analyze_path(
    target: Path,
    config: Config | None = None,
    honor_suppressions: bool = True,
) -> list[CheckResult]:
    """Analyze a ``.py`` file or every ``.py`` file under a directory."""
    if config is None:
        config = Config.default()

    files = [target] if target.is_file() else sorted(target.rglob("*.py"))
    results = []
    for file_path in files:
        if _is_excluded(file_path, config.exclude):
            continue
        source = file_path.read_text(encoding="utf-8")
        results.append(
            analyze_source(
                source,
                config,
                path=str(file_path),
                honor_suppressions=honor_suppressions,
            )
        )
    return results


def _attach_parents(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]


def _extract_comments(source: str) -> list[Comment]:
    comments: list[Comment] = []
    code_lines: set[int] = set()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return comments

    skip = {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }
    for token in tokens:
        if token.type in skip:
            continue
        for line in range(token.start[0], token.end[0] + 1):
            code_lines.add(line)

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line, col = token.start
        comments.append(
            Comment(
                line=line,
                col=col,
                text=token.string.lstrip("#").strip(),
                inline=line in code_lines,
            )
        )
    return comments


def _parse_suppressions(comments: list[Comment]) -> dict[int, set[str] | None]:
    """Map line -> suppressed rule ids on that line (``None`` = all rules)."""
    suppressions: dict[int, set[str] | None] = {}
    for comment in comments:
        match = _SUPPRESSION.search(comment.text)
        if match is None:
            continue
        ids = match.group("ids")
        if ids is None:
            suppressions[comment.line] = None
        else:
            existing = suppressions.get(comment.line)
            if existing is None and comment.line in suppressions:
                continue  # a blanket disable on this line already wins
            new_ids = {rule_id.strip() for rule_id in ids.split(",")}
            suppressions[comment.line] = (existing or set()) | new_ids
    return suppressions


def _is_suppressed(line: int, rule_id: str, suppressions: dict[int, set[str] | None]) -> bool:
    if line not in suppressions:
        return False
    ids = suppressions[line]
    return ids is None or rule_id in ids


def _is_excluded(file_path: Path, patterns: list[str]) -> bool:
    posix = file_path.resolve().as_posix()
    return any(fnmatch.fnmatch(posix, pattern) for pattern in patterns)
