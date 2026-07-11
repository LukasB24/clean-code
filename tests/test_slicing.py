"""Tests for the subscript complexity rules SL401–SL402."""


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


class TestComplexSubscript:
    def test_flags_multi_axis_slice_monster(self, check):
        source = "out = x[:, None, idx[i + 1]:idx[i + 2]:2, ::-1]\n"
        violations = check(source, "SL401")
        assert rule_ids(violations) == ["SL401"]
        assert "x[:, None, idx[i + 1]:idx[i + 2]:2, ::-1]" in violations[0].message

    def test_simple_indexing_passes(self, check):
        source = "row = grid[i]\nwindow = series[start:stop]\npair = matrix[i, j]\n"
        assert check(source, "SL401") == []

    def test_nested_subscript_is_reported_once_at_the_outer(self, check):
        source = "out = x[idx[k[m + 1]] + 1, ::-1, None]\n"
        violations = check(source, "SL401")
        assert rule_ids(violations) == ["SL401"]

    def test_threshold_is_configurable(self, check):
        source = "window = series[start:stop:2]\n"
        assert check(source, "SL401") == []
        assert rule_ids(check(source, "SL401", max_score=1)) == ["SL401"]

    def test_reversed_negative_scores_higher(self, check):
        source = "tail = values[-1]\n"
        assert check(source, "SL401") == []  # one negative index alone is fine


class TestChainedSubscript:
    def test_flags_triple_chain(self, check):
        violations = check("cell = grid[i][j][k]\n", "SL402")
        assert rule_ids(violations) == ["SL402"]
        assert "3 levels" in violations[0].message

    def test_double_chain_passes_by_default(self, check):
        assert check("cell = grid[i][j]\n", "SL402") == []

    def test_chain_reported_once_at_head(self, check):
        violations = check("cell = grid[i][j][k][m]\n", "SL402")
        assert len(violations) == 1
        assert "4 levels" in violations[0].message
