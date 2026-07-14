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


class TestEmptyExceptionHandler:
    def test_flags_pass_only_handler(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except Exception:\n"
            "        pass\n"
        )
        assert rule_ids(check(source, "PY902")) == ["PY902"]

    def test_flags_ellipsis_only_handler(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except Exception:\n"
            "        ...\n"
        )
        assert rule_ids(check(source, "PY902")) == ["PY902"]

    def test_flags_string_literal_only_handler(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except Exception:\n"
            "        'ignored'\n"
        )
        assert rule_ids(check(source, "PY902")) == ["PY902"]

    def test_flags_mixed_inert_statements(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except Exception:\n"
            "        'ignored'\n"
            "        ...\n"
            "        pass\n"
        )
        assert rule_ids(check(source, "PY902")) == ["PY902"]

    def test_bare_except_with_pass_is_also_flagged(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except:\n"
            "        pass\n"
        )
        assert rule_ids(check(source, "PY902")) == ["PY902"]

    def test_handler_that_returns_fallback_passes(self, check):
        source = (
            "def load(path):\n"
            "    try:\n"
            "        return open(path).read()\n"
            "    except Exception:\n"
            "        return None\n"
        )
        assert check(source, "PY902") == []

    def test_handler_that_logs_passes(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except Exception:\n"
            "        logger.warning('commit failed')\n"
        )
        assert check(source, "PY902") == []

    def test_handler_that_reraises_passes(self, check):
        source = (
            "def save(record):\n"
            "    try:\n"
            "        commit(record)\n"
            "    except Exception:\n"
            "        raise\n"
        )
        assert check(source, "PY902") == []

    def test_handler_that_continues_in_loop_passes(self, check):
        source = (
            "def run(items):\n"
            "    for item in items:\n"
            "        try:\n"
            "            process(item)\n"
            "        except ValueError:\n"
            "            continue\n"
        )
        assert check(source, "PY902") == []
