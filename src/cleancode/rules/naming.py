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

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import (
    FRAMING_VERBS,
    Rule,
    simple_name,
    split_identifier,
    subscript_base_name,
)

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
    lineno: int
    col_offset: int
    # The AST node the name was bound at — an ``arg``, ``Name``, or def/class/
    # handler node. Lets a rule's suggestion look at the binding's own
    # annotation or assigned value; see ``_name_hint``.
    node: ast.AST


def collect_bindings(tree: ast.Module) -> Iterator[Binding]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield Binding(node.name, KIND_FUNCTION, node.lineno, node.col_offset, node)
        elif isinstance(node, ast.ClassDef):
            yield Binding(node.name, KIND_CLASS, node.lineno, node.col_offset, node)
        elif isinstance(node, ast.arg):
            kind = KIND_LAMBDA_PARAM if _inside_lambda(node) else KIND_PARAM
            yield Binding(node.arg, kind, node.lineno, node.col_offset, node)
        elif isinstance(node, ast.ExceptHandler) and node.name is not None:
            yield Binding(node.name, KIND_EXCEPT, node.lineno, node.col_offset, node)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield Binding(node.id, _store_kind(node), node.lineno, node.col_offset, node)


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


@dataclass(frozen=True)
class _NameHint:
    """A deterministic rename candidate for a flagged binding, plus where it came from."""

    candidate: str
    source: str


# Container annotations whose *element* type names the value, not the container itself
# (`list[Trade]` is about trades, not lists).
_CONTAINER_ANNOTATIONS = frozenset({"list", "List", "set", "Set", "tuple", "Tuple", "frozenset", "FrozenSet"})

# Leading verbs stripped from a callee name before using it as a rename candidate
# (`load_users()` -> `users`), on top of the framing verbs CM301/CM304 already strip.
_IO_VERBS = frozenset({"load", "fetch", "read", "parse", "build", "retrieve", "query", "collect"})


def _name_hint(binding: Binding) -> _NameHint | None:
    node = binding.node
    if isinstance(node, ast.arg):
        return _hint_from_annotation(node.annotation) if node.annotation is not None else None
    if isinstance(node, ast.Name):
        return _hint_from_name_binding(node)
    return None


def _hint_from_name_binding(node: ast.Name) -> _NameHint | None:
    parent = getattr(node, "parent", None)
    if isinstance(parent, ast.Assign) and node in parent.targets and isinstance(parent.value, ast.Call):
        return _hint_from_call(parent.value)
    if isinstance(parent, ast.AnnAssign) and parent.target is node and parent.annotation is not None:
        return _hint_from_annotation(parent.annotation)
    return None


def _hint_from_annotation(annotation: ast.expr) -> _NameHint | None:
    leaf = _annotation_leaf_name(annotation)
    if leaf is None:
        return None
    words = split_identifier(leaf)
    if not words:
        return None
    candidate = "_".join(words)
    if isinstance(annotation, ast.Subscript) and subscript_base_name(annotation) in _CONTAINER_ANNOTATIONS:
        candidate = _pluralize(candidate)
    return _NameHint(candidate, f"its `{ast.unparse(annotation)}` annotation")


def _annotation_leaf_name(annotation: ast.expr) -> str | None:
    if isinstance(annotation, ast.Subscript) and subscript_base_name(annotation) in _CONTAINER_ANNOTATIONS:
        inner = annotation.slice
        element = inner.elts[0] if isinstance(inner, ast.Tuple) else inner
        return _annotation_leaf_name(element)
    if isinstance(annotation, ast.Name):
        return annotation.id
    if isinstance(annotation, ast.Attribute):
        return annotation.attr
    return None


def _pluralize(snake_case: str) -> str:
    *prefix, last = snake_case.split("_")
    if last.endswith(("s", "sh", "ch", "x", "z")):
        last += "es"
    elif last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    else:
        last += "s"
    return "_".join([*prefix, last])


def _hint_from_call(call: ast.Call) -> _NameHint | None:
    callee = simple_name(call.func)
    if callee is None:
        return None
    words = _strip_leading_verb(split_identifier(callee))
    if not words:
        return None  # empty, or the callee was only a verb (`load()`) — no noun left to suggest
    return _NameHint("_".join(words), f"`{callee}`")


def _strip_leading_verb(words: list[str]) -> list[str]:
    if words and (words[0] in _IO_VERBS or words[0] in FRAMING_VERBS):
        return words[1:]
    return words


def _rename_suggestion(binding: Binding, generic: str) -> str:
    hint = _name_hint(binding)
    if hint is None:
        return generic
    return f"rename to `{hint.candidate}` (from {hint.source})"


class ShortName(Rule):
    id = "NM201"
    name = "short-name"
    default_severity = Severity.WARNING
    default_options = {
        "min_length": 3,
        "allowed": ["i", "j", "k", "n", "x", "y", "_", "id", "ok", "fh"],
    }
    description = (
        "Flags names shorter than `min_length` characters (default 3) — cryptic pairs "
        "like `ab`/`bc`/`df` as much as bare letters. Conventional loop/comprehension/"
        "lambda letters (i, j, k, n, x, y) and known short words (id, ok, fh, ...) are "
        "allowlisted and configurable; functions, classes, and ordinary variables "
        "otherwise always need real names."
    )
    guidance = (
        "Give every function, class, and ordinary variable a name of at least "
        "{min_length} characters that states what the value represents — reserve "
        "short names for conventional loop/comprehension letters."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        allowed = set(ctx.config.options["allowed"])
        min_length = ctx.config.options["min_length"]
        for binding in ctx.bindings:
            if self._is_flagged(binding, allowed, min_length):
                yield self.violation(
                    ctx,
                    binding,
                    ViolationDetails(
                        message=f"short {binding.kind} `{binding.name}` "
                        f"({len(binding.name)} characters)",
                        suggestion=_rename_suggestion(
                            binding, "use a descriptive name that states what the value represents"
                        ),
                    ),
                )

    @staticmethod
    def _is_flagged(binding: Binding, allowed: set[str], min_length: int) -> bool:
        """True unless the short name is a conventional loop letter or known short word."""
        name = binding.name
        if name == "_" or len(name) >= min_length:
            return False
        if name.isupper() or (binding.kind == KIND_EXCEPT and name == "e"):
            return False
        return not ShortName._is_conventionally_short(binding, allowed)

    @staticmethod
    def _is_conventionally_short(binding: Binding, allowed: set[str]) -> bool:
        """True for a short name that's an accepted convention, not a real violation.

        Single-character names stay gated by binding kind (an ordinary variable
        named `x` is still flagged; `x` as a loop target is not). Two-or-more-
        character short names are exempt purely by allowlist, since their
        legitimacy (`id`, `ok`, `fh`) doesn't depend on where they're bound.
        """
        if len(binding.name) == 1:
            return binding.kind in _RELAXED_KINDS and binding.name in allowed
        return binding.name in allowed


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
    guidance = (
        "Never name a value tmp/data/result/foo/thing or a function "
        "process/handle/do_stuff — name it for what it holds or does (`raw_rows`, "
        "`parse_trades`)."
    )

    _NUMBERED_GENERIC = re.compile(
        r"^(data|result|res|temp|tmp|val|var|value|list|dict|arr|out|output|x|obj|item)\d+$"
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        banned = set(ctx.config.options["banned"])
        banned_functions = set(ctx.config.options["banned_functions"])
        allowed_in_loops = set(ctx.config.options["allowed_in_loops"])
        for binding in ctx.bindings:
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
                    binding,
                    ViolationDetails(
                        message=f"meaningless {binding.kind} name `{binding.name}`",
                        suggestion=_rename_suggestion(
                            binding,
                            "rename to describe the content or role, e.g. `raw_rows`, "
                            "`user_totals`, `parse_trades`",
                        ),
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
    guidance = (
        "Spell words out instead of vowel-less abbreviation soup (`usr_mgr` -> "
        "`user_manager`) unless the abbreviation is domain-standard."
    )

    _VOWELS = frozenset("aeiouy")
    _MIN_ABBREV_LENGTH = 3

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        known = set(ctx.config.options["known_abbrevs"])
        for binding in ctx.bindings:
            cryptic = [
                part
                for part in split_identifier(binding.name)
                if len(part) >= self._MIN_ABBREV_LENGTH
                and part not in known
                and not self._VOWELS & set(part)
                and part.isalpha()
            ]
            if cryptic:
                pretty = ", ".join(f"`{part}`" for part in cryptic)
                yield self.violation(
                    ctx,
                    binding,
                    ViolationDetails(
                        message=f"{binding.kind} `{binding.name}` contains cryptic "
                        f"abbreviation(s) {pretty}",
                        suggestion=(
                            "spell the word out (`usr_mgr` -> `user_manager`) or add the "
                            "abbreviation to `known_abbrevs` if it is domain-standard"
                        ),
                    ),
                )
