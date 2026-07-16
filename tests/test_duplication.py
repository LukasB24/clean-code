"""Tests for DP701/DP702 (duplicate function bodies), both ProjectRules.

Unlike the per-file rules, these need more than one parsed file to say
anything, so these tests build ``ParsedFile``s directly via
``cleancode.engine.parse_file`` and call ``check_project`` rather than using
the single-file ``check``/``analyze`` fixtures.
"""

import textwrap

from cleancode.config import Config
from cleancode.engine import analyze_path, analyze_paths, parse_file
from cleancode.rules.duplication import DuplicateFunctionBody, IdenticalFunctionImplementation


def _parsed(source: str, path: str):
    return parse_file(textwrap.dedent(source), path)


def _violations(*sources_and_paths, min_statements=4):
    files = [_parsed(source, path) for source, path in sources_and_paths]
    config = Config.default()
    config.rules["DP701"].options["min_statements"] = min_statements
    return list(DuplicateFunctionBody().check_project(files, config))


def _exact_violations(*sources_and_paths, dp701_enabled=True):
    files = [_parsed(source, path) for source, path in sources_and_paths]
    config = Config.default()
    config.rules["DP701"].enabled = dp701_enabled
    return list(IdenticalFunctionImplementation().check_project(files, config))


class TestDuplicateFunctionBody:
    def test_flags_duplicate_across_files_despite_renamed_identifiers(self):
        first = """
            def compute_totals(rows):
                total = 0
                count = 0
                for row in rows:
                    total += row.amount
                    count += 1
                return total / count
            """
        second = """
            def average_amounts(items):
                accumulator = 0
                number = 0
                for entry in items:
                    accumulator += entry.amount
                    number += 1
                return accumulator / number
            """
        violations = _violations((first, "a.py"), (second, "b.py"))
        assert [v.rule_id for v in violations] == ["DP701"]
        assert violations[0].path == "b.py"
        assert "compute_totals" in violations[0].message
        assert "a.py:2" in violations[0].message

    def test_flags_duplicate_within_the_same_file(self):
        source = """
            def compute_totals(rows):
                total = 0
                count = 0
                for row in rows:
                    total += row.amount
                    count += 1
                return total / count

            def average_amounts(items):
                accumulator = 0
                number = 0
                for entry in items:
                    accumulator += entry.amount
                    number += 1
                return accumulator / number
            """
        violations = _violations((source, "a.py"))
        assert [v.rule_id for v in violations] == ["DP701"]

    def test_permits_different_logic(self):
        first = """
            def compute_totals(rows):
                total = 0
                count = 0
                for row in rows:
                    total += row.amount
                    count += 1
                return total / count
            """
        second = """
            def format_report(rows):
                lines = []
                header = "amount"
                for row in rows:
                    lines.append(str(row.amount))
                    header += "!"
                return "\\n".join(lines)
            """
        assert _violations((first, "a.py"), (second, "b.py")) == []

    def test_permits_same_shape_calling_different_functions(self):
        # regression: called names used to be blanked with every other
        # identifier, so bodies invoking entirely different APIs collided
        first = """
            def persist(record, path):
                payload = serialize(record)
                handle = open(path, "w")
                handle.write(payload)
                return payload
            """
        second = """
            def broadcast(record, path):
                payload = encode(record)
                handle = connect(path, "w")
                handle.send(payload)
                return payload
            """
        assert _violations((first, "a.py"), (second, "b.py")) == []
        first = """
            def double(value):
                return value * 2
            """
        second = """
            def twice(number):
                return number * 2
            """
        assert _violations((first, "a.py"), (second, "b.py")) == []

    def test_permits_stub_bodies(self):
        first = """
            class Base:
                def run(self):
                    raise NotImplementedError

            class Other:
                def run(self):
                    raise NotImplementedError
            """
        assert _violations((first, "a.py"), min_statements=1) == []

    def test_permits_dunder_methods(self):
        first = """
            class First:
                def __init__(self, value):
                    self.value = value
                    self.total = 0
                    self.count = 0
                    self.name = "first"

            class Second:
                def __init__(self, value):
                    self.value = value
                    self.total = 0
                    self.count = 0
                    self.name = "second"
            """
        assert _violations((first, "a.py"), min_statements=1) == []


class TestIdenticalFunctionImplementation:
    IDENTICAL_HELPER = """
        def _is_dunder(name):
            prefix = name.startswith("__")
            return prefix and name.endswith("__")
        """

    def test_flags_exact_copy_across_files(self):
        violations = _exact_violations(
            (self.IDENTICAL_HELPER, "a.py"), (self.IDENTICAL_HELPER, "b.py")
        )
        assert [v.rule_id for v in violations] == ["DP702"]
        assert violations[0].path == "b.py"
        assert "exact copy" in violations[0].message
        assert "a.py:2" in violations[0].message

    def test_renamed_identifiers_are_not_an_exact_copy(self):
        renamed = """
            def _is_magic(label):
                prefix = label.startswith("__")
                return prefix and label.endswith("__")
            """
        assert _exact_violations((self.IDENTICAL_HELPER, "a.py"), (renamed, "b.py")) == []

    def test_single_statement_bodies_pass_by_default(self):
        helper = """
            def is_dunder(name):
                return name.startswith("__") and name.endswith("__")
            """
        assert _exact_violations((helper, "a.py"), (helper, "b.py")) == []

    def test_group_long_enough_for_dp701_is_left_to_dp701(self):
        body = """
            def compute_totals(rows):
                total = 0
                count = 0
                for row in rows:
                    total += row.amount
                    count += 1
                return total / count
            """
        assert _exact_violations((body, "a.py"), (body, "b.py")) == []
        # ... unless DP701 is disabled — then DP702 still reports the copy
        violations = _exact_violations((body, "a.py"), (body, "b.py"), dp701_enabled=False)
        assert [v.rule_id for v in violations] == ["DP702"]

    def test_stub_bodies_pass(self):
        stub = """
            class Base:
                def run(self):
                    raise NotImplementedError
            """
        assert _exact_violations((stub, "a.py"), (stub, "b.py")) == []


class TestDuplicateFunctionBodyIntegration:
    def test_analyze_path_reports_violation_on_the_later_file(self, tmp_path):
        (tmp_path / "a.py").write_text(
            "def compute_totals(rows):\n"
            "    total = 0\n"
            "    count = 0\n"
            "    for row in rows:\n"
            "        total += row.amount\n"
            "        count += 1\n"
            "    return total / count\n"
        )
        (tmp_path / "b.py").write_text(
            "def average_amounts(items):\n"
            "    accumulator = 0\n"
            "    number = 0\n"
            "    for entry in items:\n"
            "        accumulator += entry.amount\n"
            "        number += 1\n"
            "    return accumulator / number\n"
        )
        results = {result.path: result for result in analyze_path(tmp_path)}
        b_result = results[str(tmp_path / "b.py")]
        assert [v.rule_id for v in b_result.violations] == ["DP701"]
        assert results[str(tmp_path / "a.py")].violations == []

    def test_inline_suppression_on_the_flagged_file_is_honored(self, tmp_path):
        (tmp_path / "a.py").write_text(
            "def compute_totals(rows):\n"
            "    total = 0\n"
            "    count = 0\n"
            "    for row in rows:\n"
            "        total += row.amount\n"
            "        count += 1\n"
            "    return total / count\n"
        )
        (tmp_path / "b.py").write_text(
            "def average_amounts(items):  # cleancode: disable=DP701\n"
            "    accumulator = 0\n"
            "    number = 0\n"
            "    for entry in items:\n"
            "        accumulator += entry.amount\n"
            "        number += 1\n"
            "    return accumulator / number\n"
        )
        results = {result.path: result for result in analyze_path(tmp_path)}
        assert results[str(tmp_path / "b.py")].violations == []

    def test_analyze_paths_aggregates_separate_targets_into_one_project_run(self, tmp_path):
        """Two CLI targets (e.g. `clean-code check a.py b.py`) must be compared
        against each other, not analyzed as two isolated runs."""
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"
        first_dir.mkdir()
        second_dir.mkdir()
        (first_dir / "a.py").write_text(
            "def compute_totals(rows):\n"
            "    total = 0\n"
            "    count = 0\n"
            "    for row in rows:\n"
            "        total += row.amount\n"
            "        count += 1\n"
            "    return total / count\n"
        )
        (second_dir / "b.py").write_text(
            "def average_amounts(items):\n"
            "    accumulator = 0\n"
            "    number = 0\n"
            "    for entry in items:\n"
            "        accumulator += entry.amount\n"
            "        number += 1\n"
            "    return accumulator / number\n"
        )
        results = {result.path: result for result in analyze_paths([first_dir, second_dir])}
        assert [v.rule_id for v in results[str(second_dir / "b.py")].violations] == ["DP701"]
        assert results[str(first_dir / "a.py")].violations == []

    def test_analyze_paths_deduplicates_overlapping_targets(self, tmp_path):
        """`clean-code check src src/foo.py` must not analyze foo.py twice."""
        (tmp_path / "a.py").write_text(
            "def compute_totals(rows):\n"
            "    total = 0\n"
            "    count = 0\n"
            "    for row in rows:\n"
            "        total += row.amount\n"
            "        count += 1\n"
            "    return total / count\n"
        )
        (tmp_path / "b.py").write_text(
            "def average_amounts(items):\n"
            "    accumulator = 0\n"
            "    number = 0\n"
            "    for entry in items:\n"
            "        accumulator += entry.amount\n"
            "        number += 1\n"
            "    return accumulator / number\n"
        )
        results = analyze_paths([tmp_path, tmp_path / "b.py"])
        assert [result.path for result in results].count(str(tmp_path / "b.py")) == 1
        by_path = {result.path: result for result in results}
        assert [v.rule_id for v in by_path[str(tmp_path / "b.py")].violations] == ["DP701"]
