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

    def test_nested_function_body_inherits_enclosing_depth(self, check):
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
        # if(1) -> if(2) -> inner's if(3) -> if(4): visually 4 deep, not reset.
        assert check(source, "ST101", max_depth=4) == []
        violations = check(source, "ST101", max_depth=2)
        assert lines_of(violations) == [("ST101", 6)]
        assert "depth 4" in violations[0].message

    def test_deep_nesting_inside_nested_function_is_reported_once(self, check):
        source = """
        def outer():
            def inner(values):
                for value in values:
                    if value:
                        if value > 1:
                            print(value)
            return inner
        """
        # regression: this used to yield two identical violations, one attributed
        # to `outer` and one to `inner`, for the same block
        violations = check(source, "ST101", max_depth=2)
        assert lines_of(violations) == [("ST101", 6)]

    def test_match_case_offender_reports_at_pattern_line(self, check):
        # regression: a match_case as first offender crashed (no lineno of its own)
        source = """
        def dispatch(commands):
            for command in commands:
                if command:
                    match command:
                        case "start":
                            print(command)
        """
        violations = check(source, "ST101", max_depth=2)
        assert lines_of(violations) == [("ST101", 6)]

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

    def test_nested_function_branches_score_only_the_nested_function(self, check):
        # regression: inner's branches used to count toward outer's complexity too
        source = """
        def outer(values):
            def inner(value):
                if value == 1:
                    return "one"
                if value == 2:
                    return "two"
                if value == 3:
                    return "three"
                return None
            return inner
        """
        violations = check(source, "ST105", max_complexity=3)
        assert lines_of(violations) == [("ST105", 3)]
        assert "`inner`" in violations[0].message

    def test_lambda_branches_count_toward_enclosing_function(self, check):
        source = """
        def pick(values):
            chooser = lambda value: "big" if value > 1 else "small"
            return [chooser(value) for value in values if value]
        """
        # 1 base + 1 lambda ternary + 1 comprehension filter = 3
        violations = check(source, "ST105", max_complexity=2)
        assert lines_of(violations) == [("ST105", 2)]
        assert "complexity 3" in violations[0].message

    def test_comprehension_filters_count(self, check):
        source = """
        def sieve(numbers):
            return [number for number in numbers if number if number > 2]
        """
        violations = check(source, "ST105", max_complexity=2)
        assert lines_of(violations) == [("ST105", 2)]


class TestMaxModuleLength:
    def test_flags_module_over_the_limit(self, check):
        source = "\n".join(f"CONSTANT_{index} = {index}" for index in range(12))
        violations = check(source, "ST108", max_lines=10)
        assert lines_of(violations) == [("ST108", 1)]
        assert "12 lines" in violations[0].message

    def test_module_at_the_limit_passes(self, check):
        source = "\n".join(f"CONSTANT_{index} = {index}" for index in range(10))
        assert check(source, "ST108", max_lines=10) == []


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


class TestTooManyGuardClauses:
    def test_flags_three_sequential_guards_in_a_loop(self, check):
        # the motivating case: filtering interleaved with the real decision
        source = """
        def check(comments, overlap_threshold, min_words):
            for comment in comments:
                if comment.exempt:
                    continue
                if len(comment.words) < min_words:
                    continue
                if comment.code_text is None:
                    continue
                if comment.overlap >= overlap_threshold:
                    print(comment)
        """
        violations = check(source, "ST107")
        assert lines_of(violations) == [("ST107", 2)]
        assert "3 sequential guard clauses" in violations[0].message
        assert "filter/predicate" in violations[0].suggestion

    def test_two_guards_pass_by_default(self, check):
        source = """
        def process(items):
            for item in items:
                if item is None:
                    continue
                if item < 0:
                    continue
                print(item)
        """
        assert check(source, "ST107") == []

    def test_top_level_guards_also_count(self, check):
        source = """
        def load(value):
            if value is None:
                return None
            if not value.strip():
                return None
            if value.startswith("#"):
                return None
            return value.strip()
        """
        violations = check(source, "ST107")
        assert lines_of(violations) == [("ST107", 2)]

    def test_guard_with_else_does_not_count(self, check):
        source = """
        def branchy(value):
            for item in value:
                if item is None:
                    continue
                else:
                    print("noop")
                if item < 0:
                    continue
                if item > 100:
                    continue
        """
        assert check(source, "ST107") == []

    def test_multi_statement_if_body_does_not_count_as_guard(self, check):
        source = """
        def branchy(value):
            for item in value:
                if item is None:
                    log(item)
                    continue
                if item < 0:
                    continue
                if item > 100:
                    continue
        """
        assert check(source, "ST107") == []

    def test_raise_and_break_count_as_guard_exits(self, check):
        source = """
        def load(value):
            if value is None:
                raise ValueError("missing")
            if not value:
                raise ValueError("empty")
            if len(value) > 100:
                raise ValueError("too long")
            return value
        """
        violations = check(source, "ST107")
        assert lines_of(violations) == [("ST107", 2)]

    def test_threshold_is_configurable(self, check):
        source = """
        def process(items):
            for item in items:
                if item is None:
                    continue
                if item < 0:
                    continue
                print(item)
        """
        assert check(source, "ST107", max_guards=1) != []
