"""CleanCode: readability enforcer for LLM-generated Python."""

from cleancode.config import Config, ConfigError, RuleConfig
from cleancode.engine import analyze_path, analyze_source
from cleancode.models import CheckResult, Severity, Violation

__version__ = "0.2.0"

__all__ = [
    "CheckResult",
    "Config",
    "ConfigError",
    "RuleConfig",
    "Severity",
    "Violation",
    "analyze_path",
    "analyze_source",
    "__version__",
]
