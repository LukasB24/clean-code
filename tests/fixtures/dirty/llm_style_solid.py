"""Shape area calculator and a usage report, generated in one LLM pass."""


class Circle:
    def __init__(self, radius):
        self.radius = radius


class Square:
    def __init__(self, side):
        self.side = side


class Triangle:
    def __init__(self, base, height):
        self.base = base
        self.height = height


def compute_area(shape):
    if isinstance(shape, Circle):
        return 3.14159 * shape.radius * shape.radius
    elif isinstance(shape, Square):
        return shape.side * shape.side
    elif isinstance(shape, Triangle):
        return 0.5 * shape.base * shape.height
    return 0.0


class UsageReport:
    def __init__(self):
        self.total_area = 0.0
        self.shape_count = 0
        self.db_connection = None
        self.last_query_result = None

    def add_shape(self, shape):
        self.total_area += compute_area(shape)
        self.shape_count += 1

    def summarize(self):
        return f"{self.shape_count} shapes, {self.total_area} total area"

    def connect_to_database(self, dsn):
        self.db_connection = dsn

    def run_report_query(self, sql):
        self.last_query_result = f"{self.db_connection}:{sql}"
        return self.last_query_result
