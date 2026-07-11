"""Rule registry. Rules are registered explicitly — no plugin machinery."""

from cleancode.rules.base import Rule
from cleancode.rules.comments import (
    BoilerplateParamDocs,
    CommentDensity,
    CommentRestatesCode,
    DocstringRestatesName,
)
from cleancode.rules.hints import UninformativeAny
from cleancode.rules.naming import CrypticAbbreviation, MeaninglessName, SingleLetterName
from cleancode.rules.slicing import ChainedSubscript, ComplexSubscript
from cleancode.rules.structure import (
    DoOneThing,
    MaxClassLength,
    MaxComplexity,
    MaxFunctionLength,
    MaxNestingDepth,
    MaxParameters,
    TooManyGuardClauses,
)

ALL_RULES: list[type[Rule]] = [
    MaxNestingDepth,
    MaxFunctionLength,
    MaxClassLength,
    MaxParameters,
    MaxComplexity,
    DoOneThing,
    TooManyGuardClauses,
    SingleLetterName,
    MeaninglessName,
    CrypticAbbreviation,
    DocstringRestatesName,
    CommentRestatesCode,
    CommentDensity,
    BoilerplateParamDocs,
    ComplexSubscript,
    ChainedSubscript,
    UninformativeAny,
]

RULES_BY_ID: dict[str, type[Rule]] = {rule.id: rule for rule in ALL_RULES}
