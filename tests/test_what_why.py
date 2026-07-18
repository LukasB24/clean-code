"""Tests for CM307 and the semantic what/why machinery under it.

The acceptance examples from the issue that motivated the rule are asserted
here verbatim — and deliberately kept out of ``tools/data/what_why.jsonl``,
so passing proves generalization, not memorization.
"""

import json
import sys
import time
import tomllib
from pathlib import Path

import numpy as np

from cleancode.semantics.backbone import load_table
from cleancode.semantics.classifier import load_classifier
from cleancode.semantics.clauses import clauses, narration_shaped
from cleancode.semantics.training import fit_logistic_regression

REPO_ROOT = Path(__file__).parent.parent
DATASET = REPO_ROOT / "tools" / "data" / "what_why.jsonl"
HEAD = REPO_ROOT / "src" / "cleancode" / "semantics" / "head.json"


class TestClauses:
    def test_composite_splits_at_rationale_connective(self):
        parts = clauses("Computes matrix multiplication using block-striping to maximize L1 cache hits.")
        assert parts == [
            "Computes matrix multiplication using block-striping",
            "to maximize L1 cache hits",
        ]

    def test_code_span_punctuation_is_not_a_boundary(self):
        assert clauses("String elements of a ``__all__ = [...]`` assignment, in order.") == [
            "String elements of a   assignment, in order"
        ]

    def test_bare_so_starts_a_rationale_clause(self):
        assert clauses("Sorted so the fallback is deterministic.") == [
            "Sorted",
            "so the fallback is deterministic",
        ]

    def test_prepositional_to_is_not_a_boundary(self):
        assert clauses("converts the string to lowercase") == ["converts the string to lowercase"]


class TestNarrationShaped:
    def test_verb_led_narration(self):
        assert narration_shaped("Adds two numbers and returns the sum")
        assert narration_shaped("iterating over the rows")
        assert narration_shaped("This function takes the input list")

    def test_noun_led_contract_is_not_narration(self):
        assert not narration_shaped("Dotted name of the innermost enclosing function")
        assert not narration_shaped("The score paired with the reasons that drove it")

    def test_ambiguous_opener_disambiguated_by_of(self):
        assert narration_shaped("Groups the records by key")
        assert not narration_shaped("Groups of functions whose bodies collide")


class TestClassifier:
    def test_procedural_paraphrase_scores_above_default_threshold(self):
        assert load_classifier().score("Adds two numbers and returns the sum") >= 0.75

    def test_rationale_clause_scores_below_default_threshold(self):
        assert load_classifier().score("to maximize L1 cache hits") < 0.75

    def test_unknown_vocabulary_is_unjudgeable(self):
        assert load_classifier().score("qwzx bnmp vrtk") is None

    def test_scoring_is_deterministic(self):
        scores = {load_classifier().score("Iterates over the rows and sums them") for _ in range(5)}
        assert len(scores) == 1


class TestCM307Docstrings:
    def test_flags_the_issue_acceptance_example(self, check):
        source = '''
            def add(a, b):
                """Adds two numbers and returns the sum."""
                return a + b
        '''
        assert [violation.rule_id for violation in check(source, "CM307")] == ["CM307"]

    def test_passes_the_composite_acceptance_example(self, check):
        source = '''
            def matmul(matrix_a, matrix_b):
                """Computes matrix multiplication using block-striping to maximize L1 cache hits."""
                return matrix_a @ matrix_b
        '''
        assert check(source, "CM307") == []

    def test_passes_a_rationale_docstring(self, check):
        source = '''
            def totals(amounts):
                """Amounts are in cents to avoid floating-point money bugs."""
                return sum(amounts)
        '''
        assert check(source, "CM307") == []

    def test_passes_a_noun_led_value_contract(self, check):
        source = '''
            def exported_names(tree):
                """String elements of the module's public export list, in order."""
                return [element.value for element in tree.body]
        '''
        assert check(source, "CM307") == []

    def test_never_double_reports_cm301_lexical_restatements(self, check):
        source = '''
            def get_user_name(user):
                """Gets the user name."""
                return user.name
        '''
        assert check(source, "CM307") == []
        assert [violation.rule_id for violation in check(source, "CM301")] == ["CM301"]

    def test_skips_decorated_functions(self, check):
        source = '''
            import functools

            @functools.cache
            def add(a, b):
                """Adds two numbers and returns the sum."""
                return a + b
        '''
        assert check(source, "CM307") == []

    def test_skips_docstrings_longer_than_max_lines(self, check):
        source = '''
            def add(a, b):
                """Adds two numbers and returns the sum.

                Then hands the total back to the caller.
                Then does nothing else at all.
                """
                return a + b
        '''
        assert check(source, "CM307", max_lines=3) == []


class TestCM307Comments:
    def test_flags_a_paraphrasing_comment_cm302_cannot_see(self, check):
        source = '''
            def active_total(users):
                total = 0
                # walks each record and bumps the total
                for user in users:
                    if user.active:
                        total += 1
                return total
        '''
        assert [violation.rule_id for violation in check(source, "CM307")] == ["CM307"]

    def test_wrapped_comment_block_is_judged_as_one_paragraph(self, check):
        source = '''
            def refresh(cache):
                # Recomputed on demand rather than stored, because staleness
                # here is worse than the extra lookup cost.
                return cache.compute()
        '''
        assert check(source, "CM307") == []

    def test_directive_comments_are_exempt(self, check):
        source = '''
            def add(a, b):
                # TODO: walks each record and bumps the total
                return a + b
        '''
        assert check(source, "CM307") == []


class TestPerformanceBudget:
    def test_mean_scoring_time_is_well_under_a_millisecond(self):
        classifier = load_classifier()
        samples = [
            "Adds two numbers and returns the sum",
            "Iterates over the entries and appends each valid one",
            "to maximize cache locality on large batches",
            "The score paired with the reasons that drove it",
        ] * 250
        classifier.score(samples[0])  # load the table outside the timed region
        started = time.perf_counter()
        for clause in samples:
            classifier.score(clause)
        mean_seconds = (time.perf_counter() - started) / len(samples)
        assert mean_seconds < 1e-3, f"{mean_seconds * 1e6:.0f}us per clause"


class TestNoEnvironmentBloat:
    def test_no_ml_framework_is_imported(self, check):
        check("def add(a, b):\n    '''Adds two numbers and returns the sum.'''\n    return a + b")
        assert not any(module in sys.modules for module in ("torch", "sklearn", "tensorflow"))

    def test_runtime_dependencies_are_click_and_numpy_only(self):
        pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        names = sorted(spec.split(">")[0].split("=")[0] for spec in pyproject["project"]["dependencies"])
        assert names == ["click", "numpy"]


class TestHeadReproducibility:
    def test_checked_in_head_matches_retraining_on_the_checked_in_corpus(self):
        table = load_table()
        features, labels = [], []
        for line in DATASET.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            features.append(table.embed(record["text"]))
            labels.append(1 if record["label"] == "what" else 0)
        weights, bias = fit_logistic_regression(np.array(features), np.array(labels))

        head = json.loads(HEAD.read_text(encoding="utf-8"))
        assert np.allclose(weights, head["weights"], atol=1e-6)
        assert np.isclose(bias, head["bias"], atol=1e-6)
