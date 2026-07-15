#!/usr/bin/env python3
"""Measure how much clean-code's own suggestions actually improve code.

Runs the analyzer over paired ``before``/``after`` fixtures in
``tests/fixtures/benchmark/`` — each ``after`` file is the ``before`` file
with every reported violation fixed by hand, following the tool's own
``fix:`` suggestions. Reports the violation-count and severity-weighted
score delta per pair, so the improvement is a number, not a claim.

Dev-only: these fixtures aren't shipped in the wheel (see
``[tool.hatch.build.targets.wheel]`` in pyproject.toml), so this lives
outside the ``cleancode`` package rather than as a ``clean-code`` subcommand.
Run from a repo checkout with the dev extras installed:

    python scripts/benchmark.py
    python scripts/benchmark.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from cleancode.config import Config  # noqa: E402
from cleancode.engine import analyze_source  # noqa: E402

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "benchmark"
PERCENT_MULTIPLIER = 100


@dataclass(frozen=True)
class FileScore:
    violation_count: int
    score: int
    parse_error: str | None

    @classmethod
    def for_file(cls, path: Path) -> "FileScore":
        check_result = analyze_source(path.read_text(encoding="utf-8"), Config.default(), str(path))
        if check_result.parse_error:
            return cls(violation_count=0, score=0, parse_error=check_result.parse_error)
        weighted_score = sum(violation.severity.value for violation in check_result.violations)
        return cls(violation_count=len(check_result.violations), score=weighted_score, parse_error=None)


@dataclass(frozen=True)
class PairResult:
    name: str
    before: FileScore
    after: FileScore

    @property
    def improved(self) -> bool:
        return self.after.score < self.before.score

    @property
    def score_reduction_percent(self) -> float:
        if self.before.score == 0:
            return 0.0
        return PERCENT_MULTIPLIER * (self.before.score - self.after.score) / self.before.score

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "before": {"violations": self.before.violation_count, "score": self.before.score},
            "after": {"violations": self.after.violation_count, "score": self.after.score},
            "score_reduction_percent": round(self.score_reduction_percent, 1),
        }


def discover_pairs(base: Path = FIXTURES_DIR) -> list[tuple[str, Path, Path]]:
    """Match every ``before/<name>.py`` with its ``after/<name>.py`` counterpart."""
    before_dir, after_dir = base / "before", base / "after"
    before_files = sorted(before_dir.glob("*.py"))
    pairs = []
    missing = []
    for before_path in before_files:
        after_path = after_dir / before_path.name
        if not after_path.is_file():
            missing.append(before_path.name)
            continue
        pairs.append((before_path.stem, before_path, after_path))
    if missing:
        raise FileNotFoundError(
            f"before/ fixture(s) with no after/ counterpart: {', '.join(missing)}"
        )
    return pairs


def run_benchmark(base: Path = FIXTURES_DIR) -> list[PairResult]:
    return [
        PairResult(name=name, before=FileScore.for_file(before_path), after=FileScore.for_file(after_path))
        for name, before_path, after_path in discover_pairs(base)
    ]


def _format_table(pair_results: list[PairResult]) -> str:
    rows = [("fixture", "before (viol/score)", "after (viol/score)", "score reduction")]
    for pair_result in pair_results:
        rows.append(
            (
                pair_result.name,
                f"{pair_result.before.violation_count}/{pair_result.before.score}",
                f"{pair_result.after.violation_count}/{pair_result.after.score}",
                f"{pair_result.score_reduction_percent:.0f}%",
            )
        )
    widths = [max(len(row[col]) for row in rows) for col in range(4)]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths)) for row in rows
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))

    total_before_score = sum(pair_result.before.score for pair_result in pair_results)
    total_after_score = sum(pair_result.after.score for pair_result in pair_results)
    total_before_count = sum(pair_result.before.violation_count for pair_result in pair_results)
    total_after_count = sum(pair_result.after.violation_count for pair_result in pair_results)
    total_reduction = (
        PERCENT_MULTIPLIER * (total_before_score - total_after_score) / total_before_score
        if total_before_score
        else 0.0
    )
    lines.append("")
    lines.append(
        f"total: {total_before_count} -> {total_after_count} violation(s), "
        f"score {total_before_score} -> {total_after_score} "
        f"({total_reduction:.0f}% reduction)"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    try:
        pair_results = run_benchmark()
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([pair_result.to_dict() for pair_result in pair_results], indent=2))
    else:
        print(_format_table(pair_results))

    regressions = [pair_result for pair_result in pair_results if not pair_result.improved]
    if regressions:
        names = ", ".join(pair_result.name for pair_result in regressions)
        print(f"\nregression: after-fixture(s) not lower-scoring than before: {names}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
