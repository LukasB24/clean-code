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
        violations = check(source, "SD802", min_methods=2)
        assert [v.rule_id for v in violations] == ["SD802"]
