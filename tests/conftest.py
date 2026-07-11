import textwrap

import pytest

from cleancode.config import Config
from cleancode.engine import analyze_source
from cleancode.models import CheckResult


@pytest.fixture
def check():
    """Run one rule (or all) over a dedented snippet and return the violations.

    ``check(src, "ST101", max_depth=2)`` runs only ST101 with the given option
    overrides; ``check(src)`` runs every rule with defaults.
    """

    def _check(source: str, rule_id: str | None = None, **options) -> list:
        config = Config.default()
        if rule_id is not None:
            for other_id, rule_config in config.rules.items():
                rule_config.enabled = other_id == rule_id
            config.rules[rule_id].options.update(options)
        return analyze_source(textwrap.dedent(source), config).violations

    return _check


@pytest.fixture
def analyze():
    """Full-result variant of ``check`` (gives access to parse_error etc.)."""

    def _analyze(source: str, **kwargs) -> CheckResult:
        return analyze_source(textwrap.dedent(source), **kwargs)

    return _analyze
