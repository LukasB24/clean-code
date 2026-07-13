"""Tests for the SOLID-adjacent rules SD801 (type-switch-violates-ocp) and
SD802 (low-cohesion-class)."""


class TestTypeSwitchViolatesOCP:
    def test_flags_isinstance_chain_on_same_variable(self, check):
        source = """
            def area(shape):
                if isinstance(shape, Circle):
                    return 3.14
                elif isinstance(shape, Square):
                    return 1.0
                elif isinstance(shape, Triangle):
                    return 0.5
                return 0
            """
        violations = check(source, "SD801")
        assert [v.rule_id for v in violations] == ["SD801"]
        assert "`shape`" in violations[0].message

    def test_flags_type_is_chain(self, check):
        source = """
            def handle(event):
                if type(event) is Click:
                    return 1
                elif type(event) is Hover:
                    return 2
                elif type(event) is Drag:
                    return 3
            """
        assert [v.rule_id for v in check(source, "SD801")] == ["SD801"]

    def test_permits_short_chain_below_threshold(self, check):
        source = """
            def area(shape):
                if isinstance(shape, Circle):
                    return 3.14
                elif isinstance(shape, Square):
                    return 1.0
                return 0
            """
        assert check(source, "SD801") == []

    def test_permits_ast_module_type_switch(self, check):
        """Dispatching on Python's own closed ast.* hierarchy is routine AST tooling."""
        source = """
            import ast

            def describe(node):
                if isinstance(node, ast.If):
                    return "if"
                elif isinstance(node, ast.For):
                    return "for"
                elif isinstance(node, ast.While):
                    return "while"
                return "other"
            """
        assert check(source, "SD801") == []

    def test_permits_chain_on_different_variables(self, check):
        source = """
            def combine(a, b):
                if isinstance(a, int):
                    return 1
                elif isinstance(b, int):
                    return 2
                elif isinstance(a, str):
                    return 3
            """
        assert check(source, "SD801") == []

    def test_min_branches_is_configurable(self, check):
        source = """
            def area(shape):
                if isinstance(shape, Circle):
                    return 3.14
                elif isinstance(shape, Square):
                    return 1.0
            """
        assert [v.rule_id for v in check(source, "SD801", min_branches=2)] == ["SD801"]


class TestLowCohesionClass:
    def test_flags_class_with_two_unrelated_method_groups(self, check):
        source = """
            class Report:
                def __init__(self):
                    self.total = 0
                    self.currency = "usd"

                def add_amount(self, value):
                    self.total += value

                def format_total(self):
                    return f"{self.total} {self.currency}"

                def connect_database(self):
                    self.connection = object()

                def run_query(self, sql):
                    return self.connection.execute(sql)
            """
        violations = check(source, "SD802")
        assert [v.rule_id for v in violations] == ["SD802"]
        assert "Report" in violations[0].message

    def test_permits_cohesive_class(self, check):
        source = """
            class Config:
                def apply(self, section):
                    for key, value in section.items():
                        self._apply_one(key, value)

                def _apply_one(self, key, value):
                    self._store(key, value)

                def _store(self, key, value):
                    self.rules[key] = value

                def describe(self):
                    return self.rules
            """
        assert check(source, "SD802") == []

    def test_permits_small_class_below_method_floor(self, check):
        source = """
            class Report:
                def __init__(self):
                    self.total = 0
                    self.connection = None

                def add_amount(self, value):
                    self.total += value

                def connect_database(self):
                    self.connection = object()
            """
        assert check(source, "SD802") == []

    def test_permits_lone_stray_helper_alongside_a_cohesive_cluster(self, check):
        """A single method with no shared state isn't its own 'responsibility' —
        only genuine clusters of mutually-related methods count."""
        source = """
            class Report:
                def __init__(self):
                    self.total = 0
                    self.currency = "usd"

                def add_amount(self, value):
                    self.total += value

                def format_total(self):
                    return f"{self.total} {self.currency}"

                def as_percentage(self, whole):
                    return whole / 100
            """
        assert check(source, "SD802") == []

    def test_merges_property_getter_and_setter_into_one_logical_method(self, check):
        source = """
            class Point:
                def __init__(self):
                    self._x = 0
                    self.log = []

                @property
                def x(self):
                    return self._x

                @x.setter
                def x(self, value):
                    self._x = value

                def record(self, event):
                    self.log.append(event)

                def history(self):
                    return list(self.log)
            """
        assert check(source, "SD802") == []

    def test_overload_stubs_fold_into_one_logical_method(self, check):
        """@overload stubs share a name with the real implementation and must not
        inflate the raw method count the min_methods floor is gated on. This class
        has 6 raw method nodes (2 add_amount stubs + 1 impl + 3 others, forming 2
        genuine clusters) but only 4 logical names — below a floor of 5, which the
        old code (gating on the raw count) would have incorrectly let through."""
        source = """
            from typing import overload

            class Report:
                def __init__(self):
                    self.total = 0
                    self.currency = "usd"
                    self.connection = None

                @overload
                def add_amount(self, value: int) -> None: ...
                @overload
                def add_amount(self, value: float) -> None: ...
                def add_amount(self, value):
                    self.total += value

                def format_total(self):
                    return f"{self.total} {self.currency}"

                def connect_database(self):
                    self.connection = object()

                def run_query(self, sql):
                    return self.connection.execute(sql)
            """
        assert check(source, "SD802", min_methods=5) == []

    def test_permits_mixin_classes(self, check):
        """Same shape as test_flags_class_with_two_unrelated_method_groups (two
        genuinely disjoint clusters) but the *Mixin name exempts it — mixins are
        intentionally composed from independent, reusable behavior."""
        source = """
            class SingleObjectMixin:
                def __init__(self):
                    self.object_source = None
                    self.context_name = None

                def get_object(self):
                    return self.object_source

                def get_queryset(self):
                    return self.object_source

                def get_context_object_name(self):
                    return self.context_name

                def get_context_data(self):
                    return {"name": self.context_name}
            """
        assert check(source, "SD802") == []

    def test_exempt_name_suffixes_is_configurable(self, check):
        """The exemption isn't hardcoded to 'Mixin' — any project-specific naming
        convention for intentionally-composed classes can be added."""
        source = """
            class ReportImpl:
                def __init__(self):
                    self.total = 0
                    self.currency = "usd"

                def add_amount(self, value):
                    self.total += value

                def format_total(self):
                    return f"{self.total} {self.currency}"

                def connect_database(self):
                    self.connection = object()

                def run_query(self, sql):
                    return self.connection.execute(sql)
            """
        assert [v.rule_id for v in check(source, "SD802")] == ["SD802"]
        assert check(source, "SD802", exempt_name_suffixes=["Impl"]) == []

    def test_clearing_exempt_name_suffixes_still_flags_mixin_classes(self, check):
        """Confirms the *Mixin exemption is genuinely config-driven, not a
        hardcoded fallback: clearing the list removes it."""
        source = """
            class SingleObjectMixin:
                def __init__(self):
                    self.object_source = None
                    self.context_name = None

                def get_object(self):
                    return self.object_source

                def get_queryset(self):
                    return self.object_source

                def get_context_object_name(self):
                    return self.context_name

                def get_context_data(self):
                    return {"name": self.context_name}
            """
        violations = check(source, "SD802", exempt_name_suffixes=[])
        assert [v.rule_id for v in violations] == ["SD802"]

    def test_ignores_static_and_class_methods(self, check):
        source = """
            class Factory:
                def __init__(self):
                    self.total = 0

                def add_amount(self, value):
                    self.total += value

                def format_total(self):
                    return str(self.total)

                @staticmethod
                def parse(raw):
                    return int(raw)

                @classmethod
                def create(cls):
                    return cls()
            """
        assert check(source, "SD802") == []

    def test_min_methods_is_configurable(self, check):
        """Two genuine 2-member clusters is the structural minimum for this rule
        to ever fire, so configurability is demonstrated by raising the floor
        above that to suppress it, not lowering it."""
        source = """
            class Report:
                def __init__(self):
                    self.total = 0
                    self.currency = "usd"

                def add_amount(self, value):
                    self.total += value

                def format_total(self):
                    return f"{self.total} {self.currency}"

                def connect_database(self):
                    self.connection = object()

                def run_query(self, sql):
                    return self.connection.execute(sql)
            """
        assert [v.rule_id for v in check(source, "SD802")] == ["SD802"]
        assert check(source, "SD802", min_methods=5) == []
