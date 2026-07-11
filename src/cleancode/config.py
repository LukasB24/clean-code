"""Configuration model and ``[tool.cleancode]`` loader."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cleancode.models import Severity

DEFAULT_EXCLUDES = ["**/venv/**", "**/.venv/**", "**/__pycache__/**", "**/.git/**"]


class ConfigError(Exception):
    """Invalid configuration (unknown rule id, unknown option key, bad value)."""


@dataclass
class RuleConfig:
    enabled: bool = True
    severity: Severity = Severity.WARNING
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    rules: dict[str, RuleConfig] = field(default_factory=dict)
    fail_on: Severity = Severity.WARNING
    exclude: list[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))

    @classmethod
    def default(cls) -> "Config":
        from cleancode.rules import ALL_RULES

        rules = {
            rule.id: RuleConfig(
                enabled=True,
                severity=rule.default_severity,
                options=dict(rule.default_options),
            )
            for rule in ALL_RULES
        }
        return cls(rules=rules)

    @classmethod
    def load(cls, start: Path, override: Path | None = None) -> "Config":
        """Build a config from defaults merged with the nearest ``pyproject.toml``.

        ``override`` points at an explicit TOML file (``--config``); otherwise the
        loader walks up from ``start`` to the filesystem root looking for a
        ``pyproject.toml`` with a ``[tool.cleancode]`` table.
        """
        config = cls.default()
        toml_path = override if override is not None else _find_pyproject(start)
        if toml_path is None:
            return config

        with open(toml_path, "rb") as fh:
            document = tomllib.load(fh)
        section = document.get("tool", {}).get("cleancode")
        if section is None:
            return config
        config.apply_toml(section)
        return config

    def apply_toml(self, section: dict[str, Any]) -> None:
        from cleancode.rules import RULES_BY_ID

        for key, value in section.items():
            if key == "disable":
                for rule_id in _expect_str_list(key, value):
                    self._rule_config(rule_id).enabled = False
            elif key == "fail_on":
                self.fail_on = Severity.from_name(_expect_str(key, value))
            elif key == "exclude":
                self.exclude = list(DEFAULT_EXCLUDES) + _expect_str_list(key, value)
            elif key in RULES_BY_ID:
                self._apply_rule_table(key, _expect_table(key, value))
            else:
                raise ConfigError(
                    f"unknown key [tool.cleancode.{key}]: not a rule id or global option"
                )

    def _apply_rule_table(self, rule_id: str, table: dict[str, Any]) -> None:
        from cleancode.rules import RULES_BY_ID

        rule_config = self._rule_config(rule_id)
        known_options = RULES_BY_ID[rule_id].default_options
        for option, value in table.items():
            if option == "enabled":
                rule_config.enabled = bool(value)
            elif option == "severity":
                rule_config.severity = Severity.from_name(_expect_str(option, value))
            elif option in known_options:
                rule_config.options[option] = value
            else:
                valid = ", ".join(sorted(known_options)) or "(none)"
                raise ConfigError(
                    f"unknown option {option!r} for rule {rule_id}; valid options: {valid}"
                )

    def _rule_config(self, rule_id: str) -> RuleConfig:
        if rule_id not in self.rules:
            raise ConfigError(f"unknown rule id {rule_id!r}")
        return self.rules[rule_id]


def _find_pyproject(start: Path) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def _expect_str(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{key!r} must be a string, got {type(value).__name__}")
    return value


def _expect_str_list(key: str, value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key!r} must be a list of strings")
    return value


def _expect_table(key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"[tool.cleancode.{key}] must be a table")
    return value
