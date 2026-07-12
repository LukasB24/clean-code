"""Tests for the type-hint rule TY501 (uninformative-any)."""


def rule_lines(violations):
    return [(violation.rule_id, violation.line) for violation in violations]


class TestUninformativeAny:
    def test_flags_bare_any_parameter(self, check):
        source = "from typing import Any\n\n\ndef handle(payload: Any) -> None:\n    return None\n"
        violations = check(source, "TY501")
        assert rule_lines(violations) == [("TY501", 4)]
        assert "parameter `payload`" in violations[0].message

    def test_flags_bare_any_return(self, check):
        source = "from typing import Any\n\n\ndef load() -> Any:\n    return 1\n"
        violations = check(source, "TY501")
        assert [violation.rule_id for violation in violations] == ["TY501"]
        assert "return type" in violations[0].message

    def test_flags_optional_any(self, check):
        source = (
            "from typing import Any, Optional\n\n\n"
            "def maybe(value: Optional[Any]) -> None:\n    return None\n"
        )
        assert [v.rule_id for v in check(source, "TY501")] == ["TY501"]

    def test_flags_any_union_none(self, check):
        source = "from typing import Any\n\n\ndef maybe(value: Any | None) -> None:\n    return None\n"
        assert [v.rule_id for v in check(source, "TY501")] == ["TY501"]

    def test_flags_union_containing_any(self, check):
        source = (
            "from typing import Any, Union\n\n\n"
            "def maybe(value: Union[int, Any]) -> None:\n    return None\n"
        )
        assert [v.rule_id for v in check(source, "TY501")] == ["TY501"]

    def test_permits_any_nested_in_container(self, check):
        source = (
            "from typing import Any\n\n\n"
            "def merge(rows: dict[str, Any]) -> list[Any]:\n    return list(rows)\n"
        )
        assert check(source, "TY501") == []

    def test_permits_optional_structured_type(self, check):
        source = (
            "from typing import Any, Optional\n\n\n"
            "def merge(rows: Optional[dict[str, Any]]) -> None:\n    return None\n"
        )
        assert check(source, "TY501") == []

    def test_descriptive_types_pass(self, check):
        source = "def add(first: int, second: int) -> int:\n    return first + second\n"
        assert check(source, "TY501") == []

    def test_unannotated_function_is_not_flagged(self, check):
        # the rule polices Any specifically, it does not require annotations
        source = "def add(first, second):\n    return first + second\n"
        assert check(source, "TY501") == []
