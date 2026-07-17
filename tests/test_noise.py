"""Tests for the naming/indirection-ceremony rules SM620-SM622."""


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


class TestReturnedTemp:
    def test_flags_immediate_return_of_assigned_name(self, check):
        source = "def compute(x):\n    result = x * 2\n    return result\n"
        violations = check(source, "SM620")
        assert rule_ids(violations) == ["SM620"]
        assert "`result`" in violations[0].message

    def test_annotated_assignment_is_exempt(self, check):
        source = "def compute(x):\n    result: int = x * 2\n    return result\n"
        assert check(source, "SM620") == []

    def test_name_used_elsewhere_is_exempt(self, check):
        source = (
            "def compute(x):\n"
            "    result = x * 2\n"
            "    log(result)\n"
            "    return result\n"
        )
        assert check(source, "SM620") == []

    def test_returning_a_different_name_is_exempt(self, check):
        source = "def compute(x):\n    result = x * 2\n    return x\n"
        assert check(source, "SM620") == []

    def test_direct_return_of_expression_is_exempt(self, check):
        source = "def compute(x):\n    return x * 2\n"
        assert check(source, "SM620") == []

    def test_flags_inside_nested_block(self, check):
        source = (
            "def compute(x):\n"
            "    if x > 0:\n"
            "        result = x * 2\n"
            "        return result\n"
            "    return 0\n"
        )
        violations = check(source, "SM620")
        assert rule_ids(violations) == ["SM620"]


class TestCompatibilityAlias:
    def test_flags_module_level_alias_of_a_function(self, check):
        source = "def helper():\n    pass\n\n\nold_helper = helper\n"
        violations = check(source, "SM621")
        assert rule_ids(violations) == ["SM621"]
        assert "`old_helper`" in violations[0].message
        assert "`helper`" in violations[0].message

    def test_flags_module_level_alias_of_a_class(self, check):
        source = "class Widget:\n    pass\n\n\nOldWidget = Widget\n"
        assert rule_ids(check(source, "SM621")) == ["SM621"]

    def test_all_caps_alias_is_exempt(self, check):
        source = "def default_handler():\n    pass\n\n\nDEFAULT_HANDLER = default_handler\n"
        assert check(source, "SM621") == []

    def test_underscore_prefixed_alias_is_exempt(self, check):
        source = "def helper():\n    pass\n\n\n_helper = helper\n"
        assert check(source, "SM621") == []

    def test_alias_of_an_unrelated_name_is_exempt(self, check):
        source = "def helper():\n    pass\n\n\nx = some_external_value\n"
        assert check(source, "SM621") == []

    def test_annotated_assignment_is_exempt(self, check):
        source = "def helper():\n    pass\n\n\nold_helper: object = helper\n"
        assert check(source, "SM621") == []


class TestTrivialPropertyPair:
    def test_flags_mirrored_property_and_setter(self, check):
        source = (
            "class Point:\n"
            "    def __init__(self, x):\n"
            "        self._x = x\n"
            "\n"
            "    @property\n"
            "    def x(self):\n"
            "        return self._x\n"
            "\n"
            "    @x.setter\n"
            "    def x(self, value):\n"
            "        self._x = value\n"
        )
        violations = check(source, "SM622")
        assert rule_ids(violations) == ["SM622"]
        assert "`x`" in violations[0].message

    def test_getter_only_property_is_exempt(self, check):
        source = (
            "class Point:\n"
            "    def __init__(self, x):\n"
            "        self._x = x\n"
            "\n"
            "    @property\n"
            "    def x(self):\n"
            "        return self._x\n"
        )
        assert check(source, "SM622") == []

    def test_property_with_logic_is_exempt(self, check):
        source = (
            "class Point:\n"
            "    def __init__(self, x):\n"
            "        self._x = x\n"
            "\n"
            "    @property\n"
            "    def x(self):\n"
            "        return abs(self._x)\n"
            "\n"
            "    @x.setter\n"
            "    def x(self, value):\n"
            "        self._x = value\n"
        )
        assert check(source, "SM622") == []

    def test_setter_with_validation_is_exempt(self, check):
        source = (
            "class Point:\n"
            "    def __init__(self, x):\n"
            "        self._x = x\n"
            "\n"
            "    @property\n"
            "    def x(self):\n"
            "        return self._x\n"
            "\n"
            "    @x.setter\n"
            "    def x(self, value):\n"
            "        if value < 0:\n"
            "            raise ValueError('negative')\n"
            "        self._x = value\n"
        )
        assert check(source, "SM622") == []
