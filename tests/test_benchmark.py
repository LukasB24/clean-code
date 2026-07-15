"""Regression net for the before/after benchmark corpus in ``scripts/benchmark.py``.

Every ``after`` fixture is the hand-fixed result of applying clean-code's own
``fix:`` suggestions to the matching ``before`` fixture. If a future rule
change makes an ``after`` file trip violations again, that's either a false
positive to fix or a fixture to update — either way, it should fail loudly
here rather than silently rot.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from benchmark import FileScore, discover_pairs, run_benchmark  # noqa: E402


def test_discovers_at_least_one_pair():
    assert len(discover_pairs()) > 0


def test_every_before_fixture_has_violations():
    for name, before_path, _after_path in discover_pairs():
        score = FileScore.for_file(before_path)
        assert score.parse_error is None, f"{name}: before/ fixture fails to parse"
        assert score.violation_count > 0, f"{name}: before/ fixture has no violations to fix"


def test_every_after_fixture_is_clean():
    for result in run_benchmark():
        assert result.after.parse_error is None, f"{result.name}: after/ fixture fails to parse"
        assert result.after.violation_count == 0, (
            f"{result.name}: after/ fixture still has {result.after.violation_count} "
            "violation(s) — either the hand-applied fix is incomplete, or a rule "
            "change introduced a false positive"
        )


def test_every_pair_shows_improvement():
    for result in run_benchmark():
        assert result.improved, (
            f"{result.name}: after score ({result.after.score}) is not lower "
            f"than before score ({result.before.score})"
        )
