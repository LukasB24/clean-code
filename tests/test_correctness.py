"""Tests for the Python correctness rules PY9xx."""


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


class TestBareExcept:
    def test_flags_bare_except(self, check):
        source = (
            "def parse(raw):\n"
            "    try:\n"
            "        return int(raw)\n"
            "    except:\n"
            "        return 0\n"
        )
        assert rule_ids(check(source, "PY901")) == ["PY901"]

    def test_except_exception_is_not_bare(self, check):
        source = (
            "def parse(raw):\n"
            "    try:\n"
            "        return int(raw)\n"
            "    except Exception:\n"
            "        return 0\n"
        )
        assert check(source, "PY901") == []

    def test_except_named_type_is_not_bare(self, check):
        source = (
            "def parse(raw):\n"
            "    try:\n"
            "        return int(raw)\n"
            "    except ValueError:\n"
            "        return 0\n"
        )
        assert check(source, "PY901") == []

    def test_flags_each_bare_except_in_multiple_try_blocks(self, check):
        source = (
            "def run():\n"
            "    try:\n"
            "        a()\n"
            "    except:\n"
            "        pass\n"
            "    try:\n"
            "        b()\n"
            "    except:\n"
            "        pass\n"
        )
        assert rule_ids(check(source, "PY901")) == ["PY901", "PY901"]
