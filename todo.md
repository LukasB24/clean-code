# Road map

Nothing outstanding. New findings from the adversarial loop get appended below.

## Adversarial finding — 2026-07-12 14:57 UTC (a Pandas ETL / data-wrangling workflow)

### TODO: New AST Rule - Unbounded Module-Level Cache Dict
- **Description:** `_REFERENCE_CACHE` is a module-level mutable dict that grows for every distinct `path` ever passed, with no eviction, TTL, or size bound. In a long-lived process (e.g. a service looping over many reference files) this is an unbounded memory leak the linter's per-line checks can't see.
- **Target Node Type:** ast.Module (for the global assignment), ast.FunctionDef (for the write site)
- **AST Traversal Logic for Agent:** 1. Walk top-level `ast.Assign`/`ast.AnnAssign` nodes in the module body; flag any target whose annotation or inferred value is `dict`/`Dict` and whose name is module-level (not inside a function/class).
  2. Find functions that write to that name via `Subscript` assignment (`_CACHE[key] = value`) but never `del`, `.pop`, or bound its size anywhere in the module — flag as an unbounded-growth cache.

### TODO: New AST Rule - In-Place Mutation of Shared/Cached Object
- **Description:** `enrich_with_store_metadata` calls `stores.fillna(..., inplace=True)` on the exact DataFrame object stored in `_REFERENCE_CACHE`. Because the cache returns the same object by reference, this mutates shared state held by every other caller/coroutine that already grabbed a reference to it — a classic aliasing bug that plain "avoid inplace=True" style lint rules won't catch since it requires tracing the value back to a cache/global source.
- **Target Node Type:** ast.Call
- **AST Traversal Logic for Agent:** 1. For each `ast.Call` with keyword `inplace=True` (or similar mutating pandas method), resolve the receiver variable's assignment origin within the enclosing function.
  2. If the receiver was assigned from a call to a function/subscript access on a module-level global (e.g. `_load_reference_table(...)` returning from a global dict, or direct `GLOBAL_DICT[key]`), flag the mutating call as unsafe shared-state mutation.

### TODO: New AST Rule - Function Mutates Its Own Parameter In Place
- **Description:** `aggregate_daily_sales` writes `enriched["date"] = ...` directly onto the parameter it was given rather than operating on a copy, silently mutating the caller's object as an undocumented side effect. Combined with the shared-cache issue above, this compounds surprising cross-call state changes.
- **Target Node Type:** ast.FunctionDef
- **AST Traversal Logic for Agent:** 1. For each function, collect its parameter names.
  2. Walk the body for `ast.Subscript` assignment targets (`param[...] = ...`) or attribute-mutating calls (`param.method(..., inplace=True)`) where `param` is one of the function's parameters and was never reassigned to `param.copy()` first — flag as a mutate-caller's-argument smell.

<details><summary>Fixture code</summary>

```python
import pandas as pd

_REFERENCE_CACHE: dict[str, pd.DataFrame] = {}


def _load_reference_table(path: str) -> pd.DataFrame:
    """Load a lookup table (e.g. store metadata, currency rates) once and
    reuse it for every subsequent ETL run in this process."""
    if path not in _REFERENCE_CACHE:
        _REFERENCE_CACHE[path] = pd.read_csv(path)
    return _REFERENCE_CACHE[path]


def load_transactions(path: str) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["transacted_at"])


def enrich_with_store_metadata(transactions: pd.DataFrame, ref_path: str) -> pd.DataFrame:
    stores = _load_reference_table(ref_path)
    # Fill missing region codes directly on the shared cached frame so we
    # don't have to redo this cleanup on every run.
    stores.fillna({"region_code": "UNKNOWN"}, inplace=True)
    return transactions.merge(stores, on="store_id", how="left")


def aggregate_daily_sales(enriched: pd.DataFrame) -> pd.DataFrame:
    enriched["date"] = enriched["transacted_at"].dt.date
    return (
        enriched.groupby(["date", "store_id", "region_code"], as_index=False)["amount"]
        .sum()
        .rename(columns={"amount": "daily_total"})
    )


def run_daily_sales_etl(transactions_path: str, ref_path: str) -> pd.DataFrame:
    txns = load_transactions(transactions_path)
    enriched = enrich_with_store_metadata(txns, ref_path)
    return aggregate_daily_sales(enriched)


def _demo() -> None:
    import io

    txns_csv = io.StringIO("transacted_at,store_id,amount\n2026-01-01,1,10\n2026-01-01,2,5\n")
    stores_csv = io.StringIO("store_id,region_code\n1,US\n2,\n")

    txns = pd.read_csv(txns_csv, parse_dates=["transacted_at"])
    stores = pd.read_csv(stores_csv)
    _REFERENCE_CACHE["stores.csv"] = stores

    enriched = enrich_with_store_metadata(txns, "stores.csv")
    result = aggregate_daily_sales(enriched)

    assert set(result["region_code"]) == {"US", "UNKNOWN"}
    assert result["daily_total"].sum() == 15


if __name__ == "__main__":
    _demo()
```

</details>
