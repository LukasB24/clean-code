"""Docstring noise rules (CM301, CM304).

These rules deterministically detect the classic LLM docstring padding: a
docstring that restates the signature, and Args sections that document
nothing. The core trick is word-overlap between the natural-language text
and the identifiers it describes.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable, Iterator

from cleancode.models import FileContext, Severity, Violation, ViolationDetails
from cleancode.rules.base import (
    FRAMING_VERBS,
    GENERIC_PARAM_WORDS,
    FunctionNode,
    Rule,
    content_words,
    docstring_node,
    split_identifier,
)

_SECTION_HEADER = re.compile(r"^\s*(args|arguments|parameters|returns|raises|yields)\s*:\s*$", re.IGNORECASE)
_PARAM_ENTRY = re.compile(r"^\s*(?P<name>\*{0,2}\w+)\s*(?:\((?P<type>[^)]*)\))?\s*:\s*(?P<desc>.*)$")


def _signature_words(function: FunctionNode) -> set[str]:
    words = set(split_identifier(function.name))
    for arg in [
        *function.args.posonlyargs,
        *function.args.args,
        *function.args.kwonlyargs,
    ]:
        words.update(split_identifier(arg.arg))
    return words


class DocstringRestatesName(Rule):
    id = "CM301"
    name = "docstring-restates-name"
    default_severity = Severity.WARNING
    default_options = {"overlap": 0.8}
    description = (
        "Flags short docstrings whose words all come from the function signature "
        '(`def get_user_name`: """Gets the user name.""") — they cost reading time '
        "and add nothing."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        overlap_threshold = ctx.config.options["overlap"]
        for function in ctx.functions:
            docstring = ast.get_docstring(function, clean=True)
            node = docstring_node(function)
            if docstring is None or node is None:
                continue
            if len(docstring.strip().splitlines()) > 2:
                continue  # substantive multi-line docstrings are never flagged
            doc_words = content_words(docstring.splitlines()[0], extra_stopwords=FRAMING_VERBS)
            signature_words = _signature_words(function)
            if not doc_words:
                message = f"docstring of `{function.name}` carries no information"
            elif len(doc_words & signature_words) / len(doc_words) >= overlap_threshold:
                message = (
                    f"docstring of `{function.name}` only restates the function signature"
                )
            else:
                continue
            yield self.violation(
                ctx,
                node,
                ViolationDetails(
                    message=message,
                    suggestion=(
                        "delete it, or document what the name cannot say: why, edge cases, "
                        "units, invariants"
                    ),
                    symbol=function.name,
                ),
            )


class BoilerplateParamDocs(Rule):
    id = "CM304"
    name = "boilerplate-param-docs"
    default_severity = Severity.WARNING
    default_options = {"min_uninformative": 0.5}
    description = (
        "Flags Google-style Args:/Returns: sections where entries like "
        "`data: The data.` describe nothing beyond the parameter name."
    )

    def check(self, ctx: FileContext) -> Iterable[Violation]:
        min_uninformative = ctx.config.options["min_uninformative"]
        for function in ctx.functions:
            docstring = ast.get_docstring(function, clean=True)
            node = docstring_node(function)
            if docstring is None or node is None:
                continue
            entries = list(self._section_entries(docstring, function))
            if not entries:
                continue
            uninformative = [name for name, is_noise in entries if is_noise]
            if len(uninformative) / len(entries) >= min_uninformative:
                pretty = ", ".join(f"`{name}`" for name in uninformative)
                yield self.violation(
                    ctx,
                    node,
                    ViolationDetails(
                        message=f"docstring of `{function.name}` has boilerplate parameter "
                        f"docs: {pretty}",
                        suggestion=(
                            "delete entries that restate the name; document only parameters "
                            "whose meaning, units, or constraints are not obvious"
                        ),
                        symbol=function.name,
                    ),
                )

    def _section_entries(
        self, docstring: str, function: FunctionNode
    ) -> Iterator[tuple[str, bool]]:
        """Yield (entry_name, is_uninformative) for Args:/Returns: style entries."""
        in_section = False
        section_name = ""
        for line in docstring.splitlines():
            header = _SECTION_HEADER.match(line)
            if header:
                in_section = True
                section_name = header.group(1).lower()
                continue
            if not in_section:
                continue
            if line.strip() and not line.startswith((" ", "\t")):
                in_section = False  # dedented text ends the section
                continue
            entry = _PARAM_ENTRY.match(line)
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
