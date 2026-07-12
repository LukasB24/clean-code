"""Analysis engine: parse once, run every enabled rule, apply suppressions."""

from __future__ import annotations

import ast
import fnmatch
import io
import re
import tokenize
from pathlib import Path

from cleancode.config import Config
from cleancode.models import CheckResult, Comment, FileContext, ParsedFile, Violation

_SUPPRESSION = re.compile(r"cleancode:\s*disable(?:\s*=\s*(?P<ids>[A-Z]{2}\d{3}(?:\s*,\s*[A-Z]{2}\d{3})*))?")


def parse_file(source: str, path: str = "<string>") -> ParsedFile:
    """Parse ``source`` into the artifact every rule operates on. Raises ``SyntaxError``."""
    tree = ast.parse(source)
    _attach_parents(tree)
    return ParsedFile(
        path=path,
        source=source,
        lines=source.splitlines(),
        tree=tree,
        comments=_extract_comments(source),
    )


def analyze_source(
    source: str,
    config: Config | None = None,
    path: str = "<string>",
) -> CheckResult:
    """Run all enabled per-file rules over ``source`` and return the sorted violations."""
    if config is None:
        config = Config.default()

    try:
        parsed = parse_file(source, path)
    except SyntaxError as error:
        return CheckResult(path=path, parse_error=f"line {error.lineno}: {error.msg}")

    violations = _run_file_rules(parsed, config)
    violations = _finalize(violations, parsed.comments, config)
    return CheckResult(path=path, violations=violations)


def analyze_path(target: Path, config: Config | None = None) -> list[CheckResult]:
    """Analyze a ``.py`` file or every ``.py`` file under a directory."""
    return analyze_paths([target], config)


def analyze_paths(targets: list[Path], config: Config | None = None) -> list[CheckResult]:
    """Analyze every ``.py`` file reached from ``targets`` as one project run.

    Project rules (cross-file duplication, cross-file SOLID checks) only see
    files reached in the same call — pass every target together (as the CLI
    does with all its ``paths`` arguments) so duplication is caught across
    them, not just within each one in isolation.
    """
    if config is None:
        config = Config.default()

    file_paths: list[Path] = []
    for target in targets:
        file_paths.extend([target] if target.is_file() else sorted(target.rglob("*.py")))

    results: list[CheckResult] = []
    parsed_files: list[ParsedFile] = []
    for file_path in file_paths:
        if _is_excluded(file_path, config.exclude):
            continue
        path = str(file_path)
        try:
            parsed = parse_file(file_path.read_text(encoding="utf-8"), path)
        except SyntaxError as error:
            results.append(CheckResult(path=path, parse_error=f"line {error.lineno}: {error.msg}"))
            continue
        parsed_files.append(parsed)
        violations = _finalize(_run_file_rules(parsed, config), parsed.comments, config)
        results.append(CheckResult(path=path, violations=violations))

    _run_project_rules(parsed_files, config, results)
    return results


def _run_file_rules(parsed: ParsedFile, config: Config) -> list[Violation]:
    from cleancode.rules import ALL_RULES
    from cleancode.rules.base import ProjectRule

    violations: list[Violation] = []
    for rule_class in ALL_RULES:
        if issubclass(rule_class, ProjectRule):
            continue
        rule_config = config.rules[rule_class.id]
        if not rule_config.enabled:
            continue
        ctx = FileContext(
            path=parsed.path,
            source=parsed.source,
            lines=parsed.lines,
            tree=parsed.tree,
            comments=parsed.comments,
            config=rule_config,
        )
        violations.extend(rule_class().check(ctx))
    return violations


class _ProjectIndex:
    """Lookup tables ``_record_project_violation`` needs to place a violation."""

    def __init__(self, files: list[ParsedFile], results: list[CheckResult]) -> None:
        self.by_path = {file_result.path: file_result for file_result in results}
        self.suppressions_by_path = {
            parsed.path: _parse_suppressions(parsed.comments) for parsed in files
        }


def _enabled_project_rules(config: Config) -> list[type]:
    from cleancode.rules import ALL_RULES
    from cleancode.rules.base import ProjectRule

    return [
        rule_class
        for rule_class in ALL_RULES
        if issubclass(rule_class, ProjectRule) and config.rules[rule_class.id].enabled
    ]


def _run_project_rules(
    files: list[ParsedFile], config: Config, results: list[CheckResult]
) -> None:
    project_rule_classes = _enabled_project_rules(config)
    if not project_rule_classes or not files:
        return

    index = _ProjectIndex(files, results)
    for rule_class in project_rule_classes:
        for violation in rule_class().check_project(files, config):
            _record_project_violation(violation, index, config)

    for file_result in results:
        file_result.violations.sort(key=lambda violation: (violation.line, violation.col, violation.rule_id))


def _record_project_violation(violation: Violation, index: _ProjectIndex, config: Config) -> None:
    file_result = index.by_path.get(violation.path)
    if file_result is None:
        return
    suppressions = index.suppressions_by_path.get(violation.path, {})
    if config.honor_suppressions and _is_suppressed(violation.line, violation.rule_id, suppressions):
        return
    file_result.violations.append(violation)


def _finalize(violations: list[Violation], comments: list[Comment], config: Config) -> list[Violation]:
    if config.honor_suppressions:
        suppressions = _parse_suppressions(comments)
        violations = [
            violation
            for violation in violations
            if not _is_suppressed(violation.line, violation.rule_id, suppressions)
        ]
    violations.sort(key=lambda violation: (violation.line, violation.col, violation.rule_id))
    return violations


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
                lineno=line,
                col_offset=col,
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
        if match is not None:
            _record_suppression(suppressions, comment.lineno, match.group("ids"))
    return suppressions


def _record_suppression(
    suppressions: dict[int, set[str] | None], line: int, ids: str | None
) -> None:
    """Merge one ``cleancode: disable[=IDS]`` directive into the per-line map."""
    if ids is None:
        suppressions[line] = None  # a blanket disable overrides everything on the line
        return
    if line in suppressions and suppressions[line] is None:
        return  # a blanket disable already covers this line
    existing = suppressions.get(line) or set()
    suppressions[line] = existing | {rule_id.strip() for rule_id in ids.split(",")}


def _is_suppressed(line: int, rule_id: str, suppressions: dict[int, set[str] | None]) -> bool:
    if line not in suppressions:
        return False
    ids = suppressions[line]
    return ids is None or rule_id in ids


def _is_excluded(file_path: Path, patterns: list[str]) -> bool:
    posix = file_path.resolve().as_posix()
    return any(fnmatch.fnmatch(posix, pattern) for pattern in patterns)
