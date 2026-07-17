"""Tests for the expression clarity rules SM614–SM617."""


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


class TestBoolArithmetic:
    def test_flags_membership_test_added_to_counter(self, check):
        source = """
        def tally(values, seen):
            count = 0
            for value in values:
                count += value in seen
            return count
        """
        violations = check(source, "SM614")
        assert rule_ids(violations) == ["SM614"]
        assert "boolean condition as a number" in violations[0].message

    def test_flags_comparison_added_to_counter(self, check):
        source = """
        def tally(values, limit):
            count = 0
            for value in values:
                count += value > limit
            return count
        """
        assert rule_ids(check(source, "SM614")) == ["SM614"]

    def test_plain_increment_passes(self, check):
        source = """
        def tally(values, seen):
            count = 0
            for value in values:
                if value in seen:
                    count += 1
            return count
        """
        assert check(source, "SM614") == []


class TestNestedTernary:
    def test_flags_ternary_inside_ternary(self, check):
        source = """
        def label(score, strict):
            return "high" if score > 9 else ("mid" if strict else "low")
        """
        violations = check(source, "SM615")
        assert rule_ids(violations) == ["SM615"]

    def test_triple_nesting_reports_only_the_outermost(self, check):
        source = """
        def label(score):
            return "a" if score > 9 else ("b" if score > 5 else ("c" if score > 1 else "d"))
        """
        assert rule_ids(check(source, "SM615")) == ["SM615"]

    def test_single_ternary_passes(self, check):
        source = """
        def label(score):
            return "high" if score > 9 else "low"
        """
        assert check(source, "SM615") == []

    def test_ternary_in_comprehension_body_passes(self, check):
        source = """
        def labels(scores):
            return ["high" if score > 9 else "low" for score in scores]
        """
        assert check(source, "SM615") == []


class TestCallableIndirection:
    def test_flags_returned_partial(self, check):
        source = """
        from functools import partial

        def make_formatter(width):
            return partial(format, width=width)
        """
        violations = check(source, "SM616")
        assert rule_ids(violations) == ["SM616"]
        assert "functools.partial" in violations[0].message

    def test_flags_returned_lambda(self, check):
        source = """
        def make_scaler(factor):
            return lambda value: value * factor
        """
        violations = check(source, "SM616")
        assert rule_ids(violations) == ["SM616"]
        assert "lambda" in violations[0].message

    def test_flags_body_that_only_hands_back_another_function(self, check):
        source = """
        def render_exact(node):
            return node.dump()

        def pick_renderer(node):
            return render_exact
        """
        violations = check(source, "SM616")
        assert rule_ids(violations) == ["SM616"]
        assert "hand back `render_exact`" in violations[0].message

    def test_guarded_dispatch_is_not_a_bare_forward(self, check):
        # regression: a return nested inside a guard `if` is conditional
        # dispatch with a None fallthrough, not "does nothing but hand back X"
        source = """
        def render_exact(node):
            return node.dump()

        def pick_renderer(node):
            if node.kind == "exact":
                return render_exact
        """
        assert check(source, "SM616") == []

    def test_method_named_partial_is_not_functools_partial(self, check):
        # regression: `.partial(...)` used to match on the attribute name alone
        source = """
        def build_retry(retry_policy, attempts):
            return retry_policy.partial(attempts=attempts)
        """
        assert check(source, "SM616") == []

    def test_unimported_partial_name_is_not_functools_partial(self, check):
        source = """
        def configure(partial, width):
            return partial(width)
        """
        assert check(source, "SM616") == []

    def test_flags_partial_via_module_alias(self, check):
        source = """
        import functools as ft

        def make_formatter(width):
            return ft.partial(format, width=width)
        """
        violations = check(source, "SM616")
        assert rule_ids(violations) == ["SM616"]
        assert "functools.partial" in violations[0].message

    def test_decorator_returning_nested_def_passes(self, check):
        source = """
        def logged(func):
            def wrapper(*args, **kwargs):
                print(func.__name__)
                return func(*args, **kwargs)
            return wrapper
        """
        assert check(source, "SM616") == []

    def test_returning_a_call_result_passes(self, check):
        source = """
        def total(values):
            return sum(values)
        """
        assert check(source, "SM616") == []


class TestDeepExpression:
    def test_flags_calls_nested_five_deep(self, check):
        source = """
        def render(fields, renderer):
            return ", ".join(f"{name}={renderer.render(renderer.blank(name, value))}" for name, value in fields)
        """
        violations = check(source, "SM617")
        assert rule_ids(violations) == ["SM617"]
        assert "5 deep" in violations[0].message

    def test_flat_condition_chain_passes(self, check):
        # long but flat: many operations, no nesting — must NOT fire
        source = """
        import ast

        def is_type_compare(test):
            return (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.left, ast.Call)
                and isinstance(test.left.func, ast.Name)
                and bool(test.comparators)
                and isinstance(test.comparators[0], ast.Name)
            )
        """
        assert check(source, "SM617") == []

    def test_module_level_data_table_passes(self, check):
        source = """
        import re

        PATTERNS = [
            (re.compile(str(len(str(sorted([1, 2]))))), "a"),
            (re.compile(str(len(str(sorted([3, 4]))))), "b"),
        ]
        """
        assert check(source, "SM617") == []

    def test_max_depth_option_is_respected(self, check):
        source = """
        def shallow(values):
            total = sum(len(str(value)) for value in values)
            return total
        """
        assert check(source, "SM617") == []
        assert rule_ids(check(source, "SM617", max_depth=2)) == ["SM617"]
