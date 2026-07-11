"""Tests for the naming rules NM201–NM203."""


def rule_lines(violations):
    return [(violation.rule_id, violation.line) for violation in violations]


class TestSingleLetterName:
    def test_allows_i_in_for_loop(self, check):
        assert check("for i in range(3):\n    print(i)\n", "NM201") == []

    def test_allows_x_in_comprehension_and_lambda(self, check):
        source = "squares = [x * x for x in range(3)]\ndouble = lambda x: x * 2\n"
        assert check(source, "NM201") == []

    def test_allows_e_for_exceptions(self, check):
        source = """
        try:
            print(1)
        except ValueError as e:
            print(e)
        """
        assert check(source, "NM201") == []

    def test_flags_single_letter_variable(self, check):
        violations = check("d = {}\n", "NM201")
        assert rule_lines(violations) == [("NM201", 1)]

    def test_flags_single_letter_parameter_and_function(self, check):
        violations = check("def f(d):\n    return d\n", "NM201")
        assert len(violations) == 2  # both `f` and `d`

    def test_flags_unconventional_letter_even_in_loop(self, check):
        violations = check("for q in range(3):\n    print(q)\n", "NM201")
        assert rule_lines(violations) == [("NM201", 1)]

    def test_underscore_is_always_fine(self, check):
        assert check("_ = ignored()\nfor _ in range(3):\n    pass\n", "NM201") == []


class TestMeaninglessName:
    def test_flags_banned_variable_names(self, check):
        violations = check("data = load()\ntmp = data\n", "NM202")
        assert rule_lines(violations) == [("NM202", 1), ("NM202", 2)]

    def test_flags_numbered_generics(self, check):
        violations = check("data2 = load()\nresult1 = data2\n", "NM202")
        assert len(violations) == 2

    def test_flags_meaningless_function_names(self, check):
        violations = check("def do_stuff():\n    pass\n", "NM202")
        assert rule_lines(violations) == [("NM202", 1)]

    def test_allows_item_as_loop_target(self, check):
        assert check("for item in cart:\n    print(item)\n", "NM202") == []

    def test_flags_item_as_plain_variable(self, check):
        violations = check("obj = fetch()\n", "NM202")
        assert rule_lines(violations) == [("NM202", 1)]

    def test_descriptive_names_pass(self, check):
        source = "user_totals = aggregate(raw_rows)\ndef parse_trades(csv_path):\n    return csv_path\n"
        assert check(source, "NM202") == []


class TestCrypticAbbreviation:
    def test_flags_vowelless_names(self, check):
        violations = check("usr_mgr = get_manager()\n", "NM203")
        assert rule_lines(violations) == [("NM203", 1)]
        assert "usr" in violations[0].message and "mgr" in violations[0].message

    def test_known_abbreviations_pass(self, check):
        assert check("cfg = load_config()\nidx = 0\n", "NM203") == []

    def test_allowlist_is_configurable(self, check):
        assert check("mgr = get()\n", "NM203", known_abbrevs=["mgr"]) == []

    def test_normal_words_pass(self, check):
        assert check("sync_manager = build()\nnext_pointer = None\n", "NM203") == []
