"""Naming rules: single-letter, meaningless, and cryptic names (NM2xx).

All three rules look at *binding occurrences only* — the place a name is
introduced (assignment target, def, parameter, loop target, ...) — so each bad
name is reported once, never at every read.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation
from cleancode.rules.base import Rule, split_identifier

# Binding kinds. The distinction matters for context-dependent allowances.
KIND_VARIABLE = "variable"
KIND_FUNCTION = "function"
KIND_CLASS = "class"
KIND_PARAM = "parameter"
KIND_LAMBDA_PARAM = "lambda parameter"
KIND_LOOP = "loop target"
KIND_COMPREHENSION = "comprehension target"
KIND_EXCEPT = "exception name"

_LOOPY_KINDS = frozenset({KIND_LOOP, KIND_COMPREHENSION})
_RELAXED_KINDS = frozenset({KIND_LOOP, KIND_COMPREHENSION, KIND_LAMBDA_PARAM})


@dataclass(frozen=True)
class Binding:
    name: str
    kind: str
    line: int
    col: int


def collect_bindings(tree: ast.Module) -> Iterator[Binding]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield Binding(node.name, KIND_FUNCTION, node.lineno, node.col_offset)
        elif isinstance(node, ast.ClassDef):
            yield Binding(node.name, KIND_CLASS, node.lineno, node.col_offset)
        elif isinstance(node, ast.arg):
            kind = KIND_LAMBDA_PARAM if _inside_lambda(node) else KIND_PARAM
            yield Binding(node.arg, kind, node.lineno, node.col_offset)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            yield Binding(node.name, KIND_EXCEPT, node.lineno, node.col_offset)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield Binding(node.id, _store_kind(node), node.lineno, node.col_offset)


def _inside_lambda(arg: ast.arg) -> bool:
    arguments = getattr(arg, "parent", None)
    return isinstance(getattr(arguments, "parent", None), ast.Lambda)


def _store_kind(name: ast.Name) -> str:
    node: ast.AST = name
    parent = getattr(node, "parent", None)
    while isinstance(parent, (ast.Tuple, ast.List, ast.Starred)):
        node = parent
        parent = getattr(node, "parent", None)
    if isinstance(parent, (ast.For, ast.AsyncFor)) and node is parent.target:
        return KIND_LOOP
    if isinstance(parent, ast.comprehension) and node is parent.target:
        return KIND_COMPREHENSION
    return KIND_VARIABLE


class SingleLetterName(Rule):
    id = "NM201"
    name = "single-letter-name"
    default_severity = Severity.WARNING
    default_options = {"allowed": ["i", "j", "k", "n", "x", "y", "_"]}
    description = (
        "Flags single-character names. Conventional letters (i, j, k, n, x, y) are "
        "tolerated as loop/comprehension/lambda targets and `e` for exceptions; "
        "functions, classes, and ordinary variables always need real names."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        allowed = set(ctx.config.options["allowed"])
        for binding in collect_bindings(ctx.tree):
            if len(binding.name) != 1 or binding.name == "_":
                continue
            if binding.name.isupper():
                continue  # T = TypeVar("T") and friends are conventional
            if binding.kind in _RELAXED_KINDS and binding.name in allowed:
                continue
            if binding.kind == KIND_EXCEPT and binding.name == "e":
                continue
            yield self.violation(
                ctx,
                f"single-letter {binding.kind} `{binding.name}`",
                line=binding.line,
                col=binding.col,
                suggestion="use a descriptive name that states what the value represents",
            )


class MeaninglessName(Rule):
    id = "NM202"
    name = "meaningless-name"
    default_severity = Severity.WARNING
    default_options = {
        "banned": [
            "tmp", "temp", "data", "result", "res", "ret", "retval", "foo", "bar",
            "baz", "stuff", "thing", "things", "obj", "var", "info", "output",
            "my_var", "temp_var", "my_list", "my_dict", "arr", "lst", "l",
        ],
        "banned_functions": [
            "process", "handle", "run_stuff", "do_stuff", "do_it", "do_something",
            "do_work", "process_data", "handle_data", "my_func", "func", "helper",
            "do_the_thing", "main2",
        ],
        "allowed_in_loops": ["item", "value", "val", "element", "entry", "key"],
    }
    description = (
        "Flags names that say nothing about their content (tmp, data, foo, do_stuff) "
        "and numbered generics like `data2` or `result1`."
    )

    _NUMBERED_GENERIC = re.compile(
        r"^(data|result|res|temp|tmp|val|var|value|list|dict|arr|out|output|x|obj|item)\d+$"
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        banned = set(ctx.config.options["banned"])
        banned_functions = set(ctx.config.options["banned_functions"])
        allowed_in_loops = set(ctx.config.options["allowed_in_loops"])
        for binding in collect_bindings(ctx.tree):
            if binding.name.isupper():
                continue  # ALL_CAPS constants like INFO or DEFAULT are named by convention
            name = binding.name.lower()
            if binding.kind == KIND_FUNCTION:
                bad = name in banned_functions or name in banned
            elif binding.kind in _LOOPY_KINDS:
                bad = name in banned and name not in allowed_in_loops
            else:
                bad = name in banned
            if not bad and self._NUMBERED_GENERIC.match(name):
                bad = True
            if bad:
                yield self.violation(
                    ctx,
                    f"meaningless {binding.kind} name `{binding.name}`",
                    line=binding.line,
                    col=binding.col,
                    suggestion=(
                        "rename to describe the content or role, e.g. `raw_rows`, "
                        "`user_totals`, `parse_trades`"
                    ),
                )


class CrypticAbbreviation(Rule):
    id = "NM203"
    name = "cryptic-abbreviation"
    default_severity = Severity.INFO
    default_options = {
        "known_abbrevs": [
            "cfg", "ctx", "idx", "db", "fn", "env", "src", "dst", "str", "css", "tmp",
            "xml", "html", "sql", "std", "cmd", "msg", "pkg", "txt", "sdk", "api",
            "url", "uri", "gcd", "rgb", "csv", "json", "yml", "js", "ts", "np",
            "df", "kwargs", "args", "cls", "llm",
        ]
    }
    description = (
        "Flags vowel-less abbreviation soup like `usr_mgr` or `calc_rslt`. "
        "Known abbreviations (cfg, ctx, idx, ...) are allowlisted and configurable."
    )

    _VOWELS = frozenset("aeiouy")

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        known = set(ctx.config.options["known_abbrevs"])
        for binding in collect_bindings(ctx.tree):
            cryptic = [
                part
                for part in split_identifier(binding.name)
                if len(part) >= 3
                and part not in known
                and not self._VOWELS & set(part)
                and part.isalpha()
            ]
            if cryptic:
                pretty = ", ".join(f"`{part}`" for part in cryptic)
                yield self.violation(
                    ctx,
                    f"{binding.kind} `{binding.name}` contains cryptic abbreviation(s) {pretty}",
                    line=binding.line,
                    col=binding.col,
                    suggestion=(
                        "spell the word out (`usr_mgr` -> `user_manager`) or add the "
                        "abbreviation to `known_abbrevs` if it is domain-standard"
                    ),
                )
