"""Tests for the reference config template."""

import tomllib
from pathlib import Path

from click.testing import CliRunner

from cleancode.cli import main
from cleancode.config import Config
from cleancode.rules import ALL_RULES
from cleancode.template import build_config_template


class TestBuildConfigTemplate:
    def test_lists_every_rule_and_option(self):
        text = build_config_template()
        for rule in ALL_RULES:
            assert f"[tool.cleancode.{rule.id}]" in text
            assert rule.name in text
            for option in rule.default_options:
                assert option in text

    def test_template_is_valid_but_inert_toml(self):
        # fully commented: it parses, and defines no active [tool.cleancode] keys
        parsed = tomllib.loads(build_config_template())
        assert parsed.get("tool", {}).get("cleancode", {}) == {}

    def test_uncommented_block_round_trips_through_the_loader(self, tmp_path):
        # a user copies the ST101 block and edits it; the loader must accept it
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.cleancode.ST101]\nmax_depth = 1\n", encoding="utf-8"
        )
        config = Config.load(tmp_path)
        assert config.rules["ST101"].options["max_depth"] == 1

    def test_committed_example_toml_has_not_drifted(self):
        # example.toml is generated; regenerate with
        # `clean-code config-template --out example.toml` after rule changes
        committed = Path(__file__).parent.parent / "example.toml"
        assert committed.read_text(encoding="utf-8") == build_config_template()

    def test_defaults_shown_match_the_registry(self):
        text = build_config_template()
        # the ST101 default rendered in the template is the real current default
        assert "max_depth = 2" in text


class TestConfigTemplateCommand:
    def test_prints_template_to_stdout(self):
        result = CliRunner().invoke(main, ["config-template"])
        assert result.exit_code == 0
        assert "[tool.cleancode]" in result.output
        assert "ST101" in result.output and "TY501" in result.output

    def test_writes_to_out_file(self, tmp_path):
        out = tmp_path / "ref.toml"
        result = CliRunner().invoke(main, ["config-template", "--out", str(out)])
        assert result.exit_code == 0
        tomllib.loads(out.read_text(encoding="utf-8"))  # valid TOML
