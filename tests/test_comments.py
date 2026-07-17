"""Tests for the comment/docstring noise rules CM301–CM305."""


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


class TestDocstringRestatesName:
    def test_flags_signature_restatement(self, check):
        source = '''
        def get_user_name(user):
            """Gets the user name."""
            return user.name
        '''
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_flags_contentless_docstring(self, check):
        source = '''
        def frobnicate(widget):
            """Do the thing."""
            return widget
        '''
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_informative_docstring_passes(self, check):
        source = '''
        def get_user_name(user):
            """Falls back to the email local part when the profile is empty."""
            return user.name or user.email.split("@")[0]
        '''
        assert check(source, "CM301") == []

    def test_short_docstring_restating_the_body_is_caught(self, check):
        # regression: a docstring that paraphrases the function's own body
        # (not just its name/params) used to slip past CM301 entirely —
        # this is the PR reviewer's flagged real-world example
        source = '''
        def _section_entries(self, docstring, function):
            """Yield (entry_name, is_uninformative) for Args:/Returns: style entries."""
            in_section = False
            section_name = ""
            for line in docstring.splitlines():
                header = SECTION_HEADER.match(line)
                if header:
                    in_section = True
                    section_name = header.group(1).lower()
                    continue
                if not in_section:
                    continue
                if line.strip() and not line.startswith((" ", "\\t")):
                    in_section = False
                    continue
                entry = PARAM_ENTRY.match(line)
                if entry is None:
                    continue
                name = entry.group("name").lstrip("*")
                description = entry.group("desc").strip()
                if section_name in ("returns", "raises", "yields"):
                    reference = set(split_identifier(function.name))
                else:
                    reference = set(split_identifier(name))
                desc_words = content_words(description, extra_stopwords=FRAMING_VERBS)
                uninformative = desc_words <= (reference | GENERIC_PARAM_WORDS)
                yield name, uninformative
        '''
        violations = check(source, "CM301")
        assert rule_ids(violations) == ["CM301"]
        assert "_section_entries" in violations[0].message

    def test_short_docstring_using_body_vocabulary_to_add_real_info_passes(self, check):
        # a short docstring can legitimately reuse a few of the body's words
        # while still adding information the code doesn't already say
        source = '''
        def _section_entries(self, docstring, function):
            """Judges Returns/Raises/Yields entries against the function name, not a param."""
            for line in docstring.splitlines():
                pass
        '''
        assert check(source, "CM301") == []

    def test_substantive_multiline_docstring_passes(self, check):
        source = '''
        def get_user_name(user):
            """Gets the user name.

            Resolution order: profile name, then display name, then the email
            local part. Never returns an empty string.
            """
            return user.name
        '''
        assert check(source, "CM301") == []

    def test_restatement_on_the_second_line_is_caught(self, check):
        # regression: only the first line was scored; a 2-line docstring
        # that restates the signature across both lines used to slip through
        source = '''
        def get_user_name(user):
            """Gets the user name.
            Returns the name of the user."""
            return user.name
        '''
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_multiline_docstring_that_never_leaves_the_signature_is_flagged(self, check):
        source = '''
        def get_user_name(user):
            """Gets the user name.

            Returns the name for the given user.
            Gets the name of the user.
            """
            return user.name
        '''
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_multiline_docstring_with_one_informative_line_passes(self, check):
        source = '''
        def get_user_name(user):
            """Gets the user name.

            Falls back to the email local part when the profile is empty.
            """
            return user.name or user.email.split("@")[0]
        '''
        assert check(source, "CM301") == []

    def test_flags_class_docstring_restating_name(self, check):
        source = """
        class UserManager:
            \"\"\"User manager.\"\"\"

            def create(self, name):
                return name
        """
        violations = check(source, "CM301")
        assert rule_ids(violations) == ["CM301"]
        assert "UserManager" in violations[0].message

    def test_informative_class_docstring_passes(self, check):
        source = """
        class UserManager:
            \"\"\"Coordinates user lifecycle across the profile and billing services.\"\"\"

            def create(self, name):
                return name
        """
        assert check(source, "CM301") == []

    def test_overlap_threshold_default_is_0_6(self, check):
        # regression: default tightened from 0.7 to 0.6 pre-1.0.
        # doc words {path, parse, quickly, config} vs signature words
        # {path, parse, mode, config}: overlap 3/4 = 0.75 -> fires at 0.6, not 0.8
        source = '''
        def parse_config(path, mode):
            """Parse config path quickly."""
            return path
        '''
        assert rule_ids(check(source, "CM301")) == ["CM301"]
        assert check(source, "CM301", overlap=0.8) == []

    def test_private_helper_uses_the_stricter_private_overlap_threshold(self, check):
        # regression: this exact docstring/body pair (from a real PR review)
        # scored 0.625 overlap against the public default -- well under the
        # old 0.7 threshold, so it slipped past CM301 entirely
        source = '''
        def _used_elsewhere(function, name, skip):
            """True if `name` appears as a Name node anywhere in the function besides `skip`."""
            for node in ast.walk(function):
                if isinstance(node, ast.Name) and node.id == name and node not in skip:
                    return True
            return False
        '''
        assert rule_ids(check(source, "CM301")) == ["CM301"]

    def test_private_helper_with_real_information_still_passes(self, check):
        source = '''
        def _merge_config(base, overrides):
            """Overrides win on key conflicts; nested dicts are merged recursively."""
            return base
        '''
        assert check(source, "CM301") == []

    def test_private_overlap_threshold_is_configurable(self, check):
        source = '''
        def _load(path):
            """Reads the file at path."""
            return path
        '''
        assert check(source, "CM301") == []
        assert rule_ids(check(source, "CM301", private_overlap=0.1)) == ["CM301"]

    def test_dunder_method_is_not_judged_as_private(self, check):
        source = '''
        class Point:
            def __repr__(self):
                """Falls back to the default repr format when coordinates are unset."""
                return "Point"
        '''
        assert check(source, "CM301") == []


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

            More padding here.
            """
            # first we do a thing
            first = values[0]
            # then another thing entirely
            second = values[1]
            # and finally combine somehow
            third = first + second
            fourth = third * 2
            fifth = fourth - 1
            return fifth
        '''
        violations = check(source, "CM303")
        assert rule_ids(violations) == ["CM303"]

    def test_sparse_comments_pass(self, check):
        source = """
        def lean(values):
            first = values[0]
            second = values[1]
            third = first + second
            fourth = third * 2
            fifth = fourth - 1
            return fifth
        """
        assert check(source, "CM303") == []

    def test_small_functions_are_ignored(self, check):
        source = "def tiny():\n    # a comment\n    # another comment\n    return 1\n"
        assert check(source, "CM303") == []


class TestBoilerplateParamDocs:
    def test_flags_args_section_that_restates_names(self, check):
        source = '''
        def transfer(amount, account):
            """Move money between ledgers.

            Args:
                amount: The amount.
                account (str): the account

            Returns:
                The transfer.
            """
            return amount, account
        '''
        violations = check(source, "CM304")
        assert rule_ids(violations) == ["CM304"]
        assert "amount" in violations[0].message

    def test_informative_args_section_passes(self, check):
        source = '''
        def transfer(amount, account):
            """Move money between ledgers.

            Args:
                amount: Minor units (cents); must be positive.
                account: IBAN of the receiving side.
            """
            return amount, account
        '''
        assert check(source, "CM304") == []

    def test_docstring_without_sections_is_ignored(self, check):
        source = '''
        def transfer(amount, account):
            """Move money between ledgers, validating both sides."""
            return amount, account
        '''
        assert check(source, "CM304") == []


class TestFileCommentDensity:
    @staticmethod
    def _commented_module(code_lines, comment_lines):
        code = [f"CONSTANT_{index} = {index}" for index in range(code_lines)]
        comments = [f"# narration line number {index}" for index in range(comment_lines)]
        return "\n".join(comments + code) + "\n"

    def test_flags_comment_heavy_file(self, check):
        source = self._commented_module(code_lines=10, comment_lines=4)
        violations = check(source, "CM305", min_code_lines=10)
        assert rule_ids(violations) == ["CM305"]
        assert violations[0].line == 1
        assert "4 comment lines for 10 code lines" in violations[0].message
        assert "every comment" in violations[0].suggestion

    def test_file_at_the_ratio_passes(self, check):
        source = self._commented_module(code_lines=10, comment_lines=2)
        assert check(source, "CM305", min_code_lines=10) == []

    def test_small_file_passes_even_when_dense(self, check):
        source = self._commented_module(code_lines=5, comment_lines=5)
        assert check(source, "CM305", min_code_lines=10) == []

    def test_directive_comments_do_not_count(self, check):
        directives = "\n".join(
            ["# TODO: revisit", "# noqa", "# cleancode: disable=NM202", "# fmt: off"]
        )
        code = "\n".join(f"CONSTANT_{index} = {index}" for index in range(10))
        source = f"{directives}\n{code}\n"
        assert check(source, "CM305", min_code_lines=10) == []

    def test_docstring_lines_count_toward_neither_side(self, check):
        docstring = '"""Module docstring.\n\n' + "\n".join("Padding." for _ in range(20)) + '\n"""'
        source = docstring + "\n" + self._commented_module(code_lines=10, comment_lines=4)
        violations = check(source, "CM305", min_code_lines=10)
        assert rule_ids(violations) == ["CM305"]
        assert "4 comment lines for 10 code lines" in violations[0].message

    def test_inline_comments_count(self, check):
        lines = [
            f"CONSTANT_{index} = {index}  # states the value again" if index < 4 else f"CONSTANT_{index} = {index}"
            for index in range(10)
        ]
        source = "\n".join(lines) + "\n"
        violations = check(source, "CM305", min_code_lines=10)
        assert rule_ids(violations) == ["CM305"]
        assert "4 comment lines for 10 code lines" in violations[0].message


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
