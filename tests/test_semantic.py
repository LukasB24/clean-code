"""Tests for the semantic pattern rules SM601–SM611."""

import textwrap


def rule_ids(violations):
    return [violation.rule_id for violation in violations]


PROCESS_TELEMETRY = textwrap.dedent(
    """
    from typing import TypedDict

    class NodeData(TypedDict, total=False):
        id: str
        active: bool
        metrics: dict[str, float]

    def process_telemetry(
        payload: list[NodeData],
        strict: bool,
        bounds: tuple[float, float, float]
    ) -> dict[str, list[str]]:
        return {
            node['id']: [
                k for k, v in node.get('metrics', {}).items()
                if (v > bounds[0] if k.startswith('tx_') else (v < bounds[1] if strict else v == bounds[2]))
            ]
            for node in payload
            if 'id' in node and (not strict or node.get('active', False))
        }
    """
)


class TestComprehensionDensity:
    def test_flags_ternary_filtered_comprehension_nested_in_another(self, check):
        assert rule_ids(check(PROCESS_TELEMETRY, "SM601")) == ["SM601"]

    def test_single_level_comprehension_with_ternary_filter_passes(self, check):
        source = "evens = [x for x in range(10) if (True if x % 2 == 0 else False)]\n"
        assert check(source, "SM601") == []

    def test_nested_comprehension_without_ternary_filter_passes(self, check):
        source = "rows = [[y for y in range(x) if y > 0] for x in range(10)]\n"
        assert check(source, "SM601") == []


class TestAnonymousTupleIndexing:
    def test_flags_positional_index_into_tuple_param(self, check):
        violations = check(PROCESS_TELEMETRY, "SM602")
        assert rule_ids(violations) == ["SM602", "SM602", "SM602"]

    def test_variadic_tuple_param_passes(self, check):
        source = (
            "def total(items: tuple[int, ...]) -> int:\n"
            "    return items[0] + items[1]\n"
        )
        assert check(source, "SM602") == []

    def test_unpacked_tuple_param_passes(self, check):
        source = (
            "def area(size: tuple[float, float]) -> float:\n"
            "    width, height = size\n"
            "    return width * height\n"
        )
        assert check(source, "SM602") == []


class TestMagicStringBranching:
    def test_flags_ternary_gated_by_startswith(self, check):
        violations = check(PROCESS_TELEMETRY, "SM603")
        assert rule_ids(violations) == ["SM603"]

    def test_bare_if_statement_is_not_flagged(self, check):
        source = "if line.startswith('#'):\n    pass\n"
        assert check(source, "SM603") == []

    def test_ternary_with_non_constant_argument_passes(self, check):
        source = "prefix = 'tx_'\nresult = 1 if key.startswith(prefix) else 2\n"
        assert check(source, "SM603") == []


class TestRedundantBooleanTernary:
    def test_flags_true_false_ternary(self, check):
        source = "flag = True if x == 1 else False\n"
        assert rule_ids(check(source, "SM604")) == ["SM604"]

    def test_flags_reversed_false_true_ternary(self, check):
        source = "flag = False if x == 1 else True\n"
        assert rule_ids(check(source, "SM604")) == ["SM604"]

    def test_non_boolean_constants_pass(self, check):
        source = "value = 1 if x == 1 else 0\n"
        assert check(source, "SM604") == []

    def test_same_boolean_on_both_branches_passes(self, check):
        source = "value = True if x == 1 else True\n"
        assert check(source, "SM604") == []


class TestReduceInsteadOfSum:
    def test_flags_reduce_with_addition_lambda(self, check):
        source = "from functools import reduce\ntotal = reduce(lambda a, b: a + b, values)\n"
        assert rule_ids(check(source, "SM605")) == ["SM605"]

    def test_reduce_with_multiplication_lambda_passes(self, check):
        source = "from functools import reduce\ntotal = reduce(lambda a, b: a * b, values)\n"
        assert check(source, "SM605") == []

    def test_non_reduce_call_passes(self, check):
        source = "total = my_reduce(lambda a, b: a + b, values)\n"
        assert check(source, "SM605") == []


class TestRepeatedCollectionIteration:
    def test_flags_second_comprehension_over_same_subscript(self, check):
        source = """
        def split(item):
            active = [m for m in item["metrics"] if m]
            inactive = [m for m in item["metrics"] if not m]
            return active, inactive
        """
        assert rule_ids(check(source, "SM606")) == ["SM606"]

    def test_bare_name_reiteration_passes(self, check):
        source = """
        def split(rows):
            kept = [r for r in rows]
            values = [r.value for r in kept]
            return values
        """
        assert check(source, "SM606") == []

    def test_different_collections_pass(self, check):
        source = """
        def split(item):
            active = [m for m in item["metrics"]]
            names = [m for m in item["labels"]]
            return active, names
        """
        assert check(source, "SM606") == []


class TestMagicNumber:
    def test_flags_literal_in_binop(self, check):
        source = "result = threshold * 1.2\n"
        assert rule_ids(check(source, "SM607")) == ["SM607"]

    def test_ignore_listed_value_passes(self, check):
        source = "result = threshold * 2\n"
        assert check(source, "SM607") == []

    def test_named_constant_assignment_passes(self, check):
        source = "TOP_TIER_MULTIPLIER = 1.2\n"
        assert check(source, "SM607") == []


class TestNonIdiomaticEmptinessCheck:
    def test_flags_len_greater_than_zero(self, check):
        source = "if len(items) > 0:\n    pass\n"
        assert rule_ids(check(source, "SM608")) == ["SM608"]

    def test_len_compared_to_nonzero_passes(self, check):
        source = "if len(items) > 5:\n    pass\n"
        assert check(source, "SM608") == []

    def test_implicit_truthiness_passes(self, check):
        source = "if items:\n    pass\n"
        assert check(source, "SM608") == []


class TestEagerDatasetLoading:
    def test_flags_np_load_in_init(self, check):
        source = """
        class Spectrograms(torch.utils.data.Dataset):
            def __init__(self, data_dir):
                self.items = []
                for name in os.listdir(data_dir):
                    self.items.append(np.load(name))
        """
        assert rule_ids(check(source, "SM609")) == ["SM609"]

    def test_load_in_getitem_passes(self, check):
        source = """
        class Spectrograms(torch.utils.data.Dataset):
            def __init__(self, data_dir):
                self.paths = os.listdir(data_dir)

            def __getitem__(self, idx):
                return np.load(self.paths[idx])
        """
        assert check(source, "SM609") == []

    def test_non_dataset_class_passes(self, check):
        source = """
        class Loader:
            def __init__(self, data_dir):
                self.data = np.load(data_dir)
        """
        assert check(source, "SM609") == []


class TestPrematureDevicePlacement:
    def test_flags_cuda_call_in_init(self, check):
        source = """
        class Spectrograms(torch.utils.data.Dataset):
            def __init__(self, data):
                self.tensor = torch.tensor(data).cuda()
        """
        assert rule_ids(check(source, "SM610")) == ["SM610"]

    def test_flags_to_with_device_string_in_getitem(self, check):
        source = """
        class Spectrograms(torch.utils.data.Dataset):
            def __getitem__(self, idx):
                return self.tensor.to("cuda")
        """
        assert rule_ids(check(source, "SM610")) == ["SM610"]

    def test_to_without_device_arg_passes(self, check):
        source = """
        class Spectrograms(torch.utils.data.Dataset):
            def __getitem__(self, idx):
                return self.tensor.to(dtype=torch.float32)
        """
        assert check(source, "SM610") == []


class TestRedundantIsinstanceCheck:
    def test_flags_isinstance_matching_variable_annotation(self, check):
        source = """
        def get(idx):
            spec: torch.Tensor = fetch(idx)
            if not isinstance(spec, torch.Tensor):
                spec = torch.tensor(spec)
            return spec
        """
        assert rule_ids(check(source, "SM611")) == ["SM611"]

    def test_isinstance_of_different_type_passes(self, check):
        source = """
        def get(idx):
            spec: torch.Tensor = fetch(idx)
            if isinstance(spec, np.ndarray):
                spec = torch.tensor(spec)
            return spec
        """
        assert check(source, "SM611") == []

    def test_generic_annotation_passes(self, check):
        source = """
        def get(items: List[torch.Tensor]):
            if isinstance(items, torch.Tensor):
                return items
            return items[0]
        """
        assert check(source, "SM611") == []


class TestUnusedBinding:
    def test_flags_unused_import(self, check):
        source = """
        import json

        def add(a, b):
            return a + b
        """
        assert rule_ids(check(source, "SM612")) == ["SM612"]

    def test_flags_unused_from_import(self, check):
        source = """
        from collections import OrderedDict

        def add(a, b):
            return a + b
        """
        assert rule_ids(check(source, "SM612")) == ["SM612"]

    def test_used_import_passes(self, check):
        source = """
        import json

        def load(raw):
            return json.loads(raw)
        """
        assert check(source, "SM612") == []

    def test_import_used_only_in_forward_ref_annotation_passes(self, check):
        source = """
        from typing import TYPE_CHECKING

        if TYPE_CHECKING:
            from mymod import Config

        def build(cfg: "Config") -> None:
            return None
        """
        assert check(source, "SM612") == []

    def test_import_listed_in_dunder_all_passes(self, check):
        source = """
        import json

        __all__ = ["json"]
        """
        assert check(source, "SM612") == []

    def test_init_module_imports_are_exempt(self, analyze):
        from cleancode.config import Config

        source = """
        import json
        """
        config = Config.default()
        for other_id, rule_config in config.rules.items():
            rule_config.enabled = other_id == "SM612"
        assert analyze(source, config=config, path="__init__.py").violations == []

    def test_flags_unused_local_variable(self, check):
        source = """
        def load_config(path):
            raw = read(path)
            parsed_data = parse(raw)
            return raw
        """
        assert rule_ids(check(source, "SM612")) == ["SM612"]

    def test_used_local_variable_passes(self, check):
        source = """
        def load_config(path):
            raw = read(path)
            parsed_data = parse(raw)
            return parsed_data
        """
        assert check(source, "SM612") == []

    def test_deleted_variable_counts_as_used(self, check):
        # regression: `del cache` is a deliberate act, not a dead binding
        source = """
        def run():
            cache = build()
            del cache
            return None
        """
        assert check(source, "SM612") == []

    def test_underscore_prefixed_variable_passes(self, check):
        source = """
        def run():
            _ignored = compute()
            return None
        """
        assert check(source, "SM612") == []

    def test_partial_tuple_unpack_with_one_used_passes(self, check):
        source = """
        def run():
            key, value = pair()
            return key
        """
        assert check(source, "SM612") == []

    def test_tuple_unpack_all_unused_is_flagged(self, check):
        source = """
        def run():
            key, value = pair()
            return None
        """
        assert rule_ids(check(source, "SM612")) == ["SM612", "SM612"]

    def test_closure_use_in_nested_function_passes(self, check):
        source = """
        def outer():
            value = compute()
            def inner():
                return value
            return inner
        """
        assert check(source, "SM612") == []

    def test_function_calling_locals_is_exempt(self, check):
        source = """
        def run():
            secret = compute()
            return locals()
        """
        assert check(source, "SM612") == []

    def test_walrus_target_unused_is_flagged(self, check):
        source = """
        def run(items):
            if (count := len(items)) > 100:
                return True
            return False
        """
        assert rule_ids(check(source, "SM612")) == ["SM612"]

    def test_walrus_target_reused_passes(self, check):
        source = """
        def run(items):
            if (count := len(items)) > 100:
                return count
            return 0
        """
        assert check(source, "SM612") == []
class TestBuiltinShadowing:
    def test_flags_shadowing_parameters(self, check):
        source = """
        def get_user(id, type, format):
            return id, type, format
        """
        assert rule_ids(check(source, "SM613")) == ["SM613", "SM613", "SM613"]

    def test_flags_shadowing_assignment(self, check):
        source = "list = fetch_items()\n"
        assert rule_ids(check(source, "SM613")) == ["SM613"]

    def test_flags_shadowing_function_name(self, check):
        source = "def type():\n    return None\n"
        assert rule_ids(check(source, "SM613")) == ["SM613"]

    def test_flags_shadowing_for_target(self, check):
        source = "for id in range(10):\n    print(id)\n"
        assert rule_ids(check(source, "SM613")) == ["SM613"]

    def test_flags_shadowing_with_target(self, check):
        source = "with open('f') as str:\n    print(str)\n"
        assert rule_ids(check(source, "SM613")) == ["SM613"]

    def test_flags_shadowing_comprehension_target(self, check):
        source = "values = [str for str in range(10)]\n"
        assert rule_ids(check(source, "SM613")) == ["SM613"]

    def test_self_attribute_is_not_flagged(self, check):
        source = """
        class Record:
            def __init__(self, id):
                self.id = id
        """
        assert rule_ids(check(source, "SM613")) == ["SM613"]

    def test_dict_key_is_not_flagged(self, check):
        source = "record = {'id': 1, 'type': 'user'}\n"
        assert check(source, "SM613") == []

    def test_keyword_argument_at_call_site_is_not_flagged(self, check):
        source = "result = render(id=1, type='user')\n"
        assert check(source, "SM613") == []

    def test_non_watched_builtin_is_not_flagged_by_default(self, check):
        source = "copyright = 'mine'\n"
        assert check(source, "SM613") == []

    def test_ordinary_name_passes(self, check):
        source = "user_id = fetch_id()\n"
        assert check(source, "SM613") == []

    def test_custom_watched_list_narrows_scope(self, check):
        source = "list = fetch_items()\n"
        assert check(source, "SM613", watched=["id"]) == []

    def test_class_body_annotated_field_is_not_flagged(self, check):
        source = """
        class Rule:
            id: str
        """
        assert check(source, "SM613") == []

    def test_class_body_plain_assignment_field_is_not_flagged(self, check):
        source = """
        class MyRule:
            id = "SM601"
        """
        assert check(source, "SM613") == []

    def test_class_body_tuple_target_fields_are_not_flagged(self, check):
        source = """
        class Spec:
            id, type = "a", "b"
        """
        assert check(source, "SM613") == []
