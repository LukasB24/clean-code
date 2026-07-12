"""Rule registry. Rules are registered explicitly — no plugin machinery."""

from cleancode.rules.base import Rule
from cleancode.rules.comments import (
    BoilerplateParamDocs,
    CommentDensity,
    CommentRestatesCode,
    DocstringRestatesName,
)
from cleancode.rules.hints import UninformativeAny
from cleancode.rules.naming import CrypticAbbreviation, MeaninglessName, ShortName
from cleancode.rules.semantic import (
    AnonymousTupleIndexing,
    ComprehensionDensity,
    EagerDatasetLoading,
    MagicNumber,
    MagicStringBranching,
    NonIdiomaticEmptinessCheck,
    PrematureDevicePlacement,
    ReduceInsteadOfSum,
    RedundantBooleanTernary,
    RedundantIsinstanceCheck,
    RepeatedCollectionIteration,
)
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
    ShortName,
    MeaninglessName,
    CrypticAbbreviation,
    DocstringRestatesName,
    CommentRestatesCode,
    CommentDensity,
    BoilerplateParamDocs,
    ComplexSubscript,
    ChainedSubscript,
    UninformativeAny,
    ComprehensionDensity,
    AnonymousTupleIndexing,
    MagicStringBranching,
    RedundantBooleanTernary,
    ReduceInsteadOfSum,
    RepeatedCollectionIteration,
    MagicNumber,
    NonIdiomaticEmptinessCheck,
    EagerDatasetLoading,
    PrematureDevicePlacement,
    RedundantIsinstanceCheck,
]

RULES_BY_ID: dict[str, type[Rule]] = {rule.id: rule for rule in ALL_RULES}
