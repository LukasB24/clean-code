"""Config loading and validation tests."""

from pathlib import Path

import pytest

from cleancode.config import Config, ConfigError
from cleancode.models import Severity


def write_pyproject(directory: Path, body: str) -> Path:
    path = directory / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


class TestDefaults:
    def test_default_config_has_every_rule_enabled(self):
        config = Config.default()
        assert len(config.rules) == 17
        assert all(rule.enabled for rule in config.rules.values())
        assert config.fail_on == Severity.WARNING


class TestLoading:
    def test_finds_pyproject_upward_from_target(self, tmp_path):
        write_pyproject(
            tmp_path,
            "[tool.cleancode]\ndisable = ['NM203']\n\n[tool.cleancode.ST101]\nmax_depth = 2\n",
        )
        nested = tmp_path / "src" / "app"
        nested.mkdir(parents=True)
        config = Config.load(nested)
        assert config.rules["NM203"].enabled is False
        assert config.rules["ST101"].options["max_depth"] == 2

    def test_missing_section_keeps_defaults(self, tmp_path):
        write_pyproject(tmp_path, "[tool.other]\nkey = 1\n")
        config = Config.load(tmp_path)
        assert config.rules["ST101"].options["max_depth"] == 2

    def test_fail_on_and_severity_override(self, tmp_path):
        write_pyproject(
            tmp_path,
            "[tool.cleancode]\nfail_on = 'error'\n\n[tool.cleancode.CM303]\nseverity = 'error'\n",
        )
        config = Config.load(tmp_path)
        assert config.fail_on == Severity.ERROR
        assert config.rules["CM303"].severity == Severity.ERROR


class TestValidation:
    def test_unknown_rule_id_raises(self, tmp_path):
        write_pyproject(tmp_path, "[tool.cleancode]\ndisable = ['ZZ999']\n")
        with pytest.raises(ConfigError, match="ZZ999"):
            Config.load(tmp_path)

    def test_unknown_option_raises(self, tmp_path):
        write_pyproject(tmp_path, "[tool.cleancode.ST101]\nmax_deepness = 3\n")
        with pytest.raises(ConfigError, match="max_deepness"):
            Config.load(tmp_path)

    def test_unknown_top_level_key_raises(self, tmp_path):
        write_pyproject(tmp_path, "[tool.cleancode]\nshout = true\n")
        with pytest.raises(ConfigError, match="shout"):
            Config.load(tmp_path)
