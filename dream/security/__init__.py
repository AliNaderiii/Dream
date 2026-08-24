"""Dream's security package — the eight-layer defense-in-depth program.

Stage B delivers the safety floor and the approval engine:

* :mod:`dream.security.blocklist` — L3, the hardline blocklist evaluated
  before any approval logic; non-overridable.
* :mod:`dream.security.assessor` — L2 auxiliary risk classification with a
  strict schema, hard timeout and fail-closed verdicts.
* :mod:`dream.security.history` — the durable, append-only approval log.
* :mod:`dream.security.engine` — L2 mode orchestration around the floor.
"""

from dream.security.assessor import ASSESS_TIMEOUT_SECONDS, Assessment, assess, pattern_assess
from dream.security.blocklist import RULES, BlockMatch, BlockRule, ScanText, floor_refusal, scan
from dream.security.engine import (
    CONTEXT_MODES,
    MODES,
    SHELL_COMMAND_TOOLS,
    Decision,
    SecurityEngine,
    default_engine,
    reset_default_engine,
)
from dream.security.history import (
    APPROVAL_DB_ENV,
    DEFAULT_APPROVAL_DB,
    ApprovalHistory,
    ApprovalStoreError,
)

__all__ = [
    "APPROVAL_DB_ENV",
    "ASSESS_TIMEOUT_SECONDS",
    "Assessment",
    "ApprovalHistory",
    "ApprovalStoreError",
    "BlockMatch",
    "BlockRule",
    "CONTEXT_MODES",
    "DEFAULT_APPROVAL_DB",
    "Decision",
    "MODES",
    "RULES",
    "SHELL_COMMAND_TOOLS",
    "ScanText",
    "SecurityEngine",
    "assess",
    "default_engine",
    "floor_refusal",
    "pattern_assess",
    "reset_default_engine",
    "scan",
]
