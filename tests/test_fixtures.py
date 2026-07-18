"""Fixture corpus tests: dirty files must trip the expected rules, clean files none.

The clean corpus is the false-positive regression net — every false positive
found in the wild should be distilled into a file here.
"""

from pathlib import Path

import pytest

from cleancode.engine import analyze_path, analyze_source

FIXTURES = Path(__file__).parent / "fixtures"

EXPECTED_DIRTY_RULES = {
    "llm_style_processing.py": {
        "ST101",  # five levels of loops/ifs
        "ST104",  # six parameters
        "NM201",  # def do_stuff(d)
        "NM202",  # process_data, data, result, tmp, do_stuff, data2
        "NM203",  # usr_mgr
        "CM301",  # """Process the data."""
        "CM302",  # '# loop over the data' etc.
        "CM303",  # comment-heavy body
        "CM304",  # 'data: The data.'
        "SM620",  # usr_mgr = data2; return usr_mgr
    },
    "llm_style_tensor.py": {
        "SL401",  # x[:, None, idx[i+1]:idx[i+2]:2, ::-1]
        "SL402",  # x[i][0][-1]
        "NM201",  # parameter x outside a loop context
        "NM202",  # val1
    },
    "llm_style_types.py": {
        "TY501",  # payload: Any, -> Any
        "ST106",  # validate_and_store
        "ST107",  # process_items: 3 sequential guards
        "SM607",  # item > 100
    },
    "short_names_and_comments.py": {
        "ST101",  # three levels of nested for-loops
        "NM201",  # ac, bc, df
        "CM302",  # '# increase a number', '# decrease the variable', '# iterate three times'
        "CM303",  # comment-heavy body
        "SM612",  # `df` is assigned but never read
    },
    "llm_style_semantics.py": {
        "NM201",  # single-letter comprehension target `v`
        "SM601",  # dict-comp nests a list-comp filtered by a ternary
        "SM602",  # bounds[0]/bounds[1]/bounds[2] anonymous tuple access
        "SM603",  # k.startswith('tx_') ternary branch
        "SM615",  # ternary nested two deep inside the comprehension filter
    },
    "llm_style_metrics.py": {
        "ST101",  # seven levels of nested if/for
        "ST105",  # cyclomatic complexity 19
        "ST106",  # process_and_export_user_metrics
        "NM201",  # comprehension target `m`, lambda params `a`/`b`
        "SM604",  # `True if ... else False` (x2)
        "SM605",  # reduce(lambda a, b: a + b, ...)
        "SM606",  # item["metrics"] iterated twice
        "SM607",  # threshold * 1.2
        "SM608",  # len(valid_scores) > 0
    },
    "pytorch_dataset.py": {
        "NM202",  # data (x2)
        "ST101",  # nested for/if inside __init__
        "SM607",  # 1e-08
        "SM609",  # np.load(file_path) inside __init__
        "SM610",  # .cuda() inside __init__
        "CM303",  # comment-heavy __getitem__
        "CM305",  # comment-heavy file overall (7 comment lines / 32 code lines)
        "CM307",  # '# Return the total number of samples' — paraphrase CM302 misses
        "SM611",  # isinstance(spec, torch.Tensor)
    },
    "llm_style_paraphrase.py": {
        "CM307",  # synonym paraphrases in docstrings and a comment; CM301/CM302 see no overlap
    },
    "llm_style_solid.py": {
        "SD801",  # compute_area type-switches on Circle/Square/Triangle
        "SD802",  # UsageReport splits into shape-tracking vs. db-query groups
        "SM607",  # 3.14159, 0.5
        "NM203",  # dsn
    },
    "llm_style_noise.py": {
        "CM306",  # two `# ====...====` banner comments
        "CM302",  # '# Order classification' restates classify_order below it
        "ST109",  # classify_order: if/else both branches return
        "NM202",  # result = sum(...)
        "SM620",  # result = sum(...); return result
        "PY903",  # load_config: 4-statement try feeding except Exception
        "SM622",  # Order.total property/setter only mirror self._total
        "SD803",  # OrderMath: two staticmethods, no state
        "SM621",  # legacy_process_order = process_order
    },
}


@pytest.mark.parametrize("name,expected", sorted(EXPECTED_DIRTY_RULES.items()))
def test_dirty_fixture_trips_expected_rules(name, expected):
    source = (FIXTURES / "dirty" / name).read_text(encoding="utf-8")
    result = analyze_source(source, path=name)
    tripped = {violation.rule_id for violation in result.violations}
    assert tripped == expected


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "clean").glob("*.py")), ids=lambda path: path.name
)
def test_clean_fixture_has_zero_violations(path):
    source = path.read_text(encoding="utf-8")
    result = analyze_source(source, path=path.name)
    assert result.violations == [], [str(violation) for violation in result.violations]


def test_dogfood_cleancode_source_is_clean():
    """The analyzer must pass its own rules."""
    package_root = Path(__file__).parent.parent / "src" / "cleancode"
    results = analyze_path(package_root)
    problems = [
        f"{result.path}:{violation.line} {violation.rule_id} {violation.message}"
        for result in results
        for violation in result.violations
    ]
    assert problems == []
