"""Tests for the comment/docstring noise rules (CM301-CM307) and the type-hint rule (TY501)."""

import textwrap


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


class TestDocstringRestatesName:
    def test_flags_docstring_restating_short_signature(self, check):
        source = textwrap.dedent('''
            def get_user_name(user):
                """Gets the user name."""
                return user.name
            ''')
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_docstring_adding_context_passes(self, check):
        source = textwrap.dedent('''
            def get_user_name(user):
                """Falls back to the anonymized id when no display name is set."""
                return user.name
            ''')
        assert check(source, "CM301") == []

    def test_flags_class_docstring_restating_name(self, check):
        source = textwrap.dedent('''
            class UserRepository:
                """Repository for users."""

                def find(self, id):
                    return self._store.get(id)
            ''')
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_class_docstring_with_real_content_passes(self, check):
        source = textwrap.dedent('''
            class UserRepository:
                """Caches lookups for five minutes to absorb request bursts."""

                def find(self, id):
                    return self._store.get(id)
            ''')
        assert check(source, "CM301") == []

    def test_overlap_threshold_default_is_0_6(self, check):
        # {path, parse, mode, config}: overlap 3/4 = 0.75 -> fires at 0.6, not 0.8
        source = textwrap.dedent('''
            def parse(path):
                """Parses the path in the given mode using the config."""
                return _do_parse(path)
            ''')
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_private_helper_uses_the_stricter_private_overlap_threshold(self, check):
        source = textwrap.dedent('''
            def _resolve(target):
                """Resolves the target by walking up until it finds a match."""
                return _walk(target)
            ''')
        # old 0.7 threshold, so it slipped past CM301 entirely
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_public_function_at_same_overlap_passes_default_threshold(self, check):
        source = textwrap.dedent('''
            def resolve(target):
                """Resolves the target by walking up until it finds a match."""
                return _walk(target)
            ''')
        assert check(source, "CM301") == []

    def test_private_overlap_threshold_is_configurable(self, check):
        source = textwrap.dedent('''
            def _resolve(target):
                """Resolves the target by walking up until it finds a match."""
                return _walk(target)
            ''')
        assert check(source, "CM301", private_overlap=0.9) == []

    def test_dunder_is_judged_as_public_not_private(self, check):
        source = textwrap.dedent('''
            class Point:
                def __repr__(self):
                    """Returns the repr of the point."""
                    return f"Point({self.x}, {self.y})"
            ''')
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_flags_body_operator_paraphrase(self, check):
        source = textwrap.dedent('''
            def add(a, b):
                """Adds a and b and returns the sum."""
                return a + b
            ''')
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_body_paraphrase_with_why_signal_is_exempt(self, check):
        source = textwrap.dedent('''
            def add(a, b):
                """Adds a and b instead of using sum(), to avoid the overhead."""
                return a + b
            ''')
        assert check(source, "CM301") == []

    def test_body_overlap_threshold_is_configurable(self, check):
        source = textwrap.dedent('''
            def add(a, b):
                """Adds a and b and returns the sum."""
                return a + b
            ''')
        assert check(source, "CM301", body_overlap=0.95) == []

    def test_paraphrase_that_reuses_own_variable_names_passes(self, check):
        source = textwrap.dedent('''
            def branches(count):
                """Returns branches based on count."""
                if count > 0:
                    return count
                return 0
            ''')
        assert check(source, "CM301") == []


class TestBoilerplateParamDocs:
    def test_flags_uninformative_param_docs(self, check):
        source = textwrap.dedent('''
            def process(data, config):
                """Processes data.

                Args:
                    data: The data.
                    config: The config.
                """
                return _run(data, config)
            ''')
        assert rule_ids(check(source, "CM304")) == ["CM304"]

    def test_informative_param_docs_pass(self, check):
        source = textwrap.dedent('''
            def process(data, config):
                """Processes data.

                Args:
                    data: Rows already deduplicated by the caller.
                    config: Feature flags for this pipeline run.
                """
                return _run(data, config)
            ''')
        assert check(source, "CM304") == []


class TestCommentRestatesCode:
    def test_flags_inline_restatement(self, check):
        source = "counter = counter + 1  # increment counter by 1\n"
        violations = check(source, "CM302")
        assert rule_ids(violations) == ["CM302"]

    def test_flags_leading_restatement(self, check):
        source = "# loop over the users\nfor user in users:\n    print(user)\n"
        assert rule_ids(check(source, "CM302")) == ["CM302"]

    def test_why_comment_passes(self, check):
        source = (
            "counter = counter + 1  # compensate for the header row skipped above\n"
        )
        assert check(source, "CM302") == []

    def test_todo_and_directives_are_exempt(self, check):
        source = (
            "counter = counter + 1  # TODO: increment counter by 1\n"
            "flag = compute_flag()  # type: ignore\n"
        )
        assert check(source, "CM302") == []

    def test_banner_comment_is_exempt_even_with_high_word_overlap(self, check):
        # A section banner is CM306's territory, not a restatement — a
        # banner that happens to reuse the following line's vocabulary
        # (here "sweep") must not also fire CM302.
        source = (
            'config["learning_rate"] = 0.01\n'
            "# --- W&B sweep overrides -------------------------------------------------------\n"
            'config["sweep_override"] = True\n'
        )
        assert check(source, "CM302") == []
        assert rule_ids(check(source, "CM306")) == ["CM306"]

    def test_return_restatement(self, check):
        source = "def total_of(items):\n    total = sum(items)\n    return total  # return the total\n"
        assert rule_ids(check(source, "CM302")) == ["CM302"]

    def test_flags_restatement_diluted_by_generic_filler_words(self, check):
        source = "count += 1  # increase a number\ncount -= 1  # decrease the variable\n"
        violations = check(source, "CM302")
        assert rule_ids(violations) == ["CM302", "CM302"]

    def test_flags_spelled_out_repeat_count(self, check):
        source = "for k in range(3):  # iterate three times\n    pass\n"
        assert rule_ids(check(source, "CM302")) == ["CM302"]

    def test_flags_spelled_out_repeat_count_variant(self, check):
        source = "for x in range(5):  # loop five times\n    pass\n"
        assert rule_ids(check(source, "CM302")) == ["CM302"]

    def test_why_signal_exempts_even_high_overlap_comment(self, check):
        # Without the "since" why-signal this scores 0.75 overlap and would
        # be flagged (verified) — the exemption must override that.
        source = "# check it matches, since equal\nif x == 1:\n    pass\n"
        assert check(source, "CM302") == []

    def test_inflected_synonym_still_matches_base_dict_entry(self, check):
        # The dict only stores "increment"; the stemmer must still match
        # "increments" against it now that the plural entry is gone.
        source = "score = score + 1  # increments the score\n"
        assert rule_ids(check(source, "CM302")) == ["CM302"]

    def test_inflected_why_signal_still_exempts(self, check):
        # The dict only stores "avoid"; "avoiding" must still exempt the
        # comment now that the "-ing" entry is gone.
        source = "counter = counter + 1  # avoiding an off-by-one\n"
        assert check(source, "CM302") == []


class TestCommentDensity:
    def test_flags_comment_heavy_function(self, check):
        source = '''
        def padded(values):
            """Docstring line one.

            Docstring line two.
            """
            # step 1
            total = 0
            # step 2
            for value in values:
                # add it
                total += value
            # step 3
            return total
        '''
        assert rule_ids(check(source, "CM303")) == ["CM303"]

    def test_sparse_comments_pass(self, check):
        source = '''
        def clean(values):
            total = 0
            for value in values:
                total += value
            return total
        '''
        assert check(source, "CM303") == []

    def test_short_function_below_min_lines_passes(self, check):
        source = '''
        def tiny():
            # a comment
            return 1
        '''
        assert check(source, "CM303") == []

    def test_max_ratio_is_configurable(self, check):
        source = '''
        def padded(values):
            # step 1
            total = 0
            # step 2
            for value in values:
                total += value
            return total
        '''
        assert check(source, "CM303", max_ratio=0.9) == []


class TestFileCommentDensity:
    def test_flags_dense_file(self, check):
        lines = []
        for i in range(20):
            lines.append(f"# comment number {i}")
            lines.append(f"value_{i} = {i}")
        source = "\n".join(lines) + "\n"
        assert rule_ids(check(source, "CM305", min_code_lines=10)) == ["CM305"]

    def test_sparse_file_passes(self, check):
        lines = []
        for i in range(20):
            lines.append(f"value_{i} = {i}")
        source = "\n".join(lines) + "\n"
        assert check(source, "CM305", min_code_lines=10) == []

    def test_directive_comments_do_not_count(self, check):
        lines = []
        for i in range(20):
            lines.append("# TODO: revisit")
            lines.append(f"value_{i} = {i}")
        source = "\n".join(lines) + "\n"
        assert check(source, "CM305", min_code_lines=10) == []

    def test_docstrings_do_not_count_toward_density(self, check):
        lines = ['"""', "Module docstring spanning", "several lines of text.", '"""']
        for i in range(20):
            lines.append(f"value_{i} = {i}")
        source = "\n".join(lines) + "\n"
        assert check(source, "CM305", min_code_lines=10) == []

    def test_below_min_code_lines_never_flagged(self, check):
        lines = []
        for i in range(5):
            lines.append(f"# comment {i}")
            lines.append(f"value_{i} = {i}")
        source = "\n".join(lines) + "\n"
        assert check(source, "CM305", min_code_lines=10) == []


class TestBannerComment:
    def test_flags_decoration_only_comment(self, check):
        source = "# ----------\nx = 1\n"
        violations = check(source, "CM306")
        assert rule_ids(violations) == ["CM306"]

    def test_flags_decoration_framed_comment(self, check):
        source = "# ---- Step 1 ----\nx = 1\n"
        violations = check(source, "CM306")
        assert rule_ids(violations) == ["CM306"]

    def test_flags_equals_sign_banner(self, check):
        source = "# ============================\nx = 1\n"
        assert rule_ids(check(source, "CM306")) == ["CM306"]

    def test_plain_narrative_comment_passes(self, check):
        source = "# Step 1: parse the input\nx = 1\n"
        assert check(source, "CM306") == []

    def test_todo_directive_is_exempt(self, check):
        source = "# TODO: -----\nx = 1\n"
        assert check(source, "CM306") == []

    def test_short_dashes_below_threshold_pass(self, check):
        source = "# --\nx = 1\n"
        assert check(source, "CM306") == []
