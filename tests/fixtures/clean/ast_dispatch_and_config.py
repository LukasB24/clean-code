"""AST node labeling and a small, cohesive settings loader."""

import ast


def label_statement(node):
    if isinstance(node, ast.If):
        return "conditional"
    elif isinstance(node, ast.For):
        return "loop"
    elif isinstance(node, ast.While):
        return "loop"
    return "other"


class Settings:
    def __init__(self):
        self.values = {}

    def apply(self, section):
        for key, value in section.items():
            self._apply_one(key, value)

    def _apply_one(self, key, value):
        self._store(key, value)

    def _store(self, key, value):
        self.values[key] = value

    def describe(self):
        return dict(self.values)
