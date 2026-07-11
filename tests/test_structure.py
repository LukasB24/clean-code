"""Tests for the structural rules ST101–ST105."""


def lines_of(violations):
    return [(violation.rule_id, violation.line) for violation in violations]


class TestMaxNestingDepth:
    def test_flags_deep_nesting_once_at_first_offender(self, check):
        source = """
        def deep(values):
            for outer in values:          # depth 1
                if outer:                 # depth 2
                    for inner in outer:   # depth 3
                        if inner:         # depth 4
                            if inner > 1: # depth 5 -> violation
                                print(inner)
        """
        violations = check(source, "ST101", max_depth=4)
        assert lines_of(violations) == [("ST101", 7)]
        assert "depth 5" in violations[0].message

    def test_accepts_configured_limit(self, check):
        source = """
        def shallow(values):
            for value in values:
                if value:
                    print(value)
        """
        assert check(source, "ST101", max_depth=2) == []

    def test_nested_function_resets_depth(self, check):
        source = """
        def outer(values):
            if values:
                if values[0]:
                    def inner():
                        if True:
                            if True:
                                return 1
                    return inner
        """
        assert check(source, "ST101", max_depth=4) == []

    def test_try_and_with_count_as_levels(self, check):
        source = """
        def risky(path):
            with open(path) as handle:
                try:
                    for line in handle:
                        if line:
                            print(line)
                except OSError:
                    pass
        """
        violations = check(source, "ST101", max_depth=3)
        assert [violation.rule_id for violation in violations] == ["ST101"]


class TestMaxFunctionLength:
    def test_flags_long_function(self, check):
        body = "\n".join(f"    step_{index} = {index}" for index in range(12))
        source = f"def long_function():\n{body}\n"
        violations = check(source, "ST102", max_lines=10)
        assert lines_of(violations) == [("ST102", 1)]
        assert "13 lines" in violations[0].message

    def test_docstring_counts_toward_length(self, check):
        source = '''
        def padded():
            """One.

            Two.
            Three.
            """
            return 1
        '''
        assert check(source, "ST102", max_lines=5) != []

    def test_short_function_passes(self, check):
        assert check("def tiny():\n    return 1\n", "ST102") == []


class TestMaxClassLength:
    def test_flags_long_class(self, check):
        methods = "\n".join(
            f"    def method_{index}(self):\n        return {index}" for index in range(6)
        )
        source = f"class Big:\n{methods}\n"
        violations = check(source, "ST103", max_lines=10)
        assert lines_of(violations) == [("ST103", 1)]


class TestMaxParameters:
    def test_flags_too_many_parameters(self, check):
        source = "def wide(alpha, beta, gamma, delta):\n    return alpha\n"
        violations = check(source, "ST104", max_params=3)
        assert lines_of(violations) == [("ST104", 1)]
        assert "4 parameters" in violations[0].message

    def test_self_and_star_args_do_not_count(self, check):
        source = """
        class Service:
            def call(self, first, second, third, *extras, **options):
                return first
        """
        assert check(source, "ST104", max_params=3) == []

    def test_keyword_only_params_count(self, check):
        source = "def wide(first, *, second, third, fourth):\n    return first\n"
        assert check(source, "ST104", max_params=3) != []


class TestMaxComplexity:
    def test_flags_branch_heavy_function(self, check):
        source = """
        def branchy(value):
            if value == 1:
                return "one"
            if value == 2:
                return "two"
            if value == 3 and value > 0:
                return "three"
            for index in range(value):
                if index:
                    return index
            return None
        """
        violations = check(source, "ST105", max_complexity=5)
        assert lines_of(violations) == [("ST105", 2)]
        assert "complexity 7" in violations[0].message

    def test_simple_function_passes(self, check):
        source = """
        def plain(value):
            if value:
                return value
            return None
        """
        assert check(source, "ST105") == []

    def test_comprehension_filters_count(self, check):
        source = """
        def sieve(numbers):
            return [number for number in numbers if number if number > 2]
        """
        violations = check(source, "ST105", max_complexity=2)
        assert lines_of(violations) == [("ST105", 2)]
