"""Tests for the generation-time briefing (`clean-code guide`)."""

from pathlib import Path

from click.testing import CliRunner

from cleancode.cli import main
from cleancode.config import Config
from cleancode.guide import COVERED_BY_SIBLING, build_agents_md, build_guide
from cleancode.rules import ALL_RULES, RULES_BY_ID

# ~2050 tokens at ~4 chars/token — generous for a 52-rule set, still cheap
# to prime an LLM with on every generation turn.
_MAX_GUIDE_CHARS = 8200


class TestBuildGuide:
    def test_every_rule_has_guidance_or_a_sibling(self):
        for rule in ALL_RULES:
            if rule.guidance is None:
                assert rule.id in COVERED_BY_SIBLING, (
                    f"{rule.id} has no guidance and isn't in COVERED_BY_SIBLING"
                )

    def test_covered_by_sibling_points_at_a_real_rule_with_guidance(self):
        for rule_id, sibling_id in COVERED_BY_SIBLING.items():
            assert sibling_id in RULES_BY_ID
            assert RULES_BY_ID[sibling_id].guidance is not None

    def test_every_guidance_string_formats_against_its_default_options(self):
        for rule in ALL_RULES:
            if rule.guidance is None:
                continue
            rule.guidance.format(**rule.default_options)  # raises on a bad placeholder

    def test_lists_every_enabled_rule_with_guidance(self):
        text = build_guide(Config.default())
        for rule in ALL_RULES:
            if rule.guidance is not None:
                assert rule.guidance.format(**rule.default_options) in text

    def test_respects_configured_option_values(self):
        config = Config.default()
        config.rules["ST101"].options["max_depth"] = 5
        text = build_guide(config)
        assert "Nest at most 5 levels" in text
        assert "Nest at most 2 levels" not in text

    def test_disabled_rule_drops_out(self):
        config = Config.default()
        config.rules["NM203"].enabled = False
        text = build_guide(config)
        assert "abbreviation" not in text

    def test_within_length_budget(self):
        assert len(build_guide(Config.default())) <= _MAX_GUIDE_CHARS

    def test_ends_with_a_check_reminder(self):
        text = build_guide(Config.default())
        assert "clean-code check" in text


class TestBuildAgentsMd:
    def test_wraps_guide_with_standing_instructions(self):
        text = build_agents_md(Config.default())
        assert "## Python style (enforced by clean-code)" in text
        assert "never suppress a violation" in text
        assert "Nest at most 2 levels" in text


class TestGuideCommand:
    def test_prints_guide_to_stdout(self):
        result = CliRunner().invoke(main, ["guide", "."])
        assert result.exit_code == 0
        assert "## Structure" in result.output

    def test_agents_md_flag(self):
        result = CliRunner().invoke(main, ["guide", ".", "--agents-md"])
        assert result.exit_code == 0
        assert "## Python style (enforced by clean-code)" in result.output

    def test_honors_project_config(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "[tool.cleancode.ST101]\nmax_depth = 4\n", encoding="utf-8"
        )
        result = CliRunner().invoke(main, ["guide", str(tmp_path)])
        assert result.exit_code == 0
        assert "Nest at most 4 levels" in result.output
