"""Tests for the comment/docstring noise rules CM301–CM304."""


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
