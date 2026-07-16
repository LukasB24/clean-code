"""Rule registry. Rules are registered explicitly — no plugin machinery."""

from cleancode.rules.base import ProjectRule, Rule
from cleancode.rules.bindings import (
    BuiltinShadowing,
    RedundantIsinstanceCheck,
    UnusedBinding,
)
from cleancode.rules.comments import (
    CommentDensity,
    CommentRestatesCode,
    FileCommentDensity,
)
from cleancode.rules.correctness import BareExcept, EmptyExceptionHandler
from cleancode.rules.docstrings import BoilerplateParamDocs, DocstringRestatesName
from cleancode.rules.duplication import DuplicateFunctionBody, IdenticalFunctionImplementation
from cleancode.rules.hints import UninformativeAny
from cleancode.rules.naming import CrypticAbbreviation, MeaninglessName, ShortName
from cleancode.rules.pytorch import EagerDatasetLoading, PrematureDevicePlacement
from cleancode.rules.semantic import (
    AnonymousTupleIndexing,
    ComprehensionDensity,
    MagicNumber,
    MagicStringBranching,
    NonIdiomaticEmptinessCheck,
    ReduceInsteadOfSum,
    RedundantBooleanTernary,
    RepeatedCollectionIteration,
)
from cleancode.rules.slicing import ChainedSubscript, ComplexSubscript
from cleancode.rules.solid import LowCohesionClass, TypeSwitchViolatesOCP
from cleancode.rules.structure import (
    DoOneThing,
    MaxClassLength,
    MaxComplexity,
    MaxFunctionLength,
    MaxModuleLength,
    MaxNestingDepth,
    MaxParameters,
    TooManyGuardClauses,
)

ALL_RULES: list[type[Rule] | type[ProjectRule]] = [
    MaxNestingDepth,
    MaxFunctionLength,
    MaxClassLength,
    MaxParameters,
    MaxComplexity,
    DoOneThing,
    TooManyGuardClauses,
    MaxModuleLength,
    ShortName,
    MeaninglessName,
    CrypticAbbreviation,
    DocstringRestatesName,
    CommentRestatesCode,
    CommentDensity,
    BoilerplateParamDocs,
    FileCommentDensity,
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
    UnusedBinding,
    BuiltinShadowing,
    TypeSwitchViolatesOCP,
    LowCohesionClass,
    DuplicateFunctionBody,
    IdenticalFunctionImplementation,
    BareExcept,
    EmptyExceptionHandler,
]

RULES_BY_ID: dict[str, type[Rule] | type[ProjectRule]] = {rule.id: rule for rule in ALL_RULES}
