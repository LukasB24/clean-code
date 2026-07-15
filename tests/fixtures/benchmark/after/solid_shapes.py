"""Shape area calculator and a usage report, split along single responsibilities."""

import math
from abc import ABC, abstractmethod

TRIANGLE_HEIGHT_FACTOR = 0.5


class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        raise NotImplementedError


class Circle(Shape):
    def __init__(self, radius: float) -> None:
        self.radius = radius

    def area(self) -> float:
        return math.pi * self.radius * self.radius


class Square(Shape):
    def __init__(self, side: float) -> None:
        self.side = side

    def area(self) -> float:
        return self.side * self.side


class Triangle(Shape):
    def __init__(self, base: float, height: float) -> None:
        self.base = base
        self.height = height

    def area(self) -> float:
        return TRIANGLE_HEIGHT_FACTOR * self.base * self.height


class ShapeUsageReport:
    def __init__(self) -> None:
        self.total_area = 0.0
        self.shape_count = 0

    def add_shape(self, shape: Shape) -> None:
        self.total_area += shape.area()
        self.shape_count += 1

    def summarize(self) -> str:
        return f"{self.shape_count} shapes, {self.total_area} total area"


class ReportDatabaseClient:
    def __init__(self) -> None:
        self.connection_string: str | None = None
        self.last_query_result: str | None = None

    def connect(self, connection_string: str) -> None:
        self.connection_string = connection_string

    def run_query(self, sql: str) -> str:
        self.last_query_result = f"{self.connection_string}:{sql}"
        return self.last_query_result
