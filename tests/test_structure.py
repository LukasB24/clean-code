"""Tests for the structural rules ST101–ST106."""


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


class TestDoOneThing:
    def test_flags_and_joined_name(self, check):
        violations = check("def load_and_save(record):\n    return record\n", "ST106")
        assert lines_of(violations) == [("ST106", 1)]
        assert "`and`" in violations[0].message

    def test_flags_or_joined_name(self, check):
        violations = check("def fetch_or_default(key):\n    return key\n", "ST106")
        assert lines_of(violations) == [("ST106", 1)]

    def test_flags_camelcase_conjunction(self, check):
        violations = check("def loadAndSave(record):\n    return record\n", "ST106")
        assert lines_of(violations) == [("ST106", 1)]

    def test_flags_methods_too(self, check):
        source = """
        class Store:
            def read_and_write(self, item):
                return item
        """
        assert [v.rule_id for v in check(source, "ST106")] == ["ST106"]

    def test_single_purpose_name_passes(self, check):
        assert check("def normalize(value):\n    return value\n", "ST106") == []

    def test_substring_conjunctions_do_not_false_positive(self, check):
        # 'and'/'or' inside a single word must not trigger
        source = (
            "def standardize(x):\n    return x\n\n"
            "def reorder(items):\n    return items\n\n"
            "def command(action):\n    return action\n"
        )
        assert check(source, "ST106") == []

    def test_dunder_methods_are_exempt(self, check):
        source = """
        class Node:
            def __init_and_setup__(self):
                pass
        """
        assert check(source, "ST106") == []

    def test_allowed_names_config(self, check):
        source = "def get_or_create(key):\n    return key\n"
        assert check(source, "ST106", allowed_names=["get_or_create"]) == []

    def test_conjunctions_config_can_drop_or(self, check):
        source = "def read_or_none(key):\n    return key\n"
        assert check(source, "ST106", conjunctions=["and"]) == []
