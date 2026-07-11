"""Rule registry. Rules are registered explicitly — no plugin machinery."""

from cleancode.rules.base import Rule
from cleancode.rules.comments import (
    BoilerplateParamDocs,
    CommentDensity,
    CommentRestatesCode,
    DocstringRestatesName,
)
from cleancode.rules.naming import CrypticAbbreviation, MeaninglessName, SingleLetterName
from cleancode.rules.slicing import ChainedSubscript, ComplexSubscript
from cleancode.rules.structure import (
    MaxClassLength,
    MaxComplexity,
    MaxFunctionLength,
    MaxNestingDepth,
    MaxParameters,
)

ALL_RULES: list[type[Rule]] = [
    MaxNestingDepth,
    MaxFunctionLength,
    MaxClassLength,
    MaxParameters,
    MaxComplexity,
    SingleLetterName,
    MeaninglessName,
    CrypticAbbreviation,
    DocstringRestatesName,
    CommentRestatesCode,
    CommentDensity,
    BoilerplateParamDocs,
    ComplexSubscript,
    ChainedSubscript,
]

RULES_BY_ID: dict[str, type[Rule]] = {rule.id: rule for rule in ALL_RULES}
