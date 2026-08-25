"""Dream's security package — the eight-layer defense-in-depth program.

Stage B delivers the safety floor and the approval engine:

* :mod:`dream.security.blocklist` — L3, the hardline blocklist evaluated
  before any approval logic; non-overridable.
* :mod:`dream.security.assessor` — L2 auxiliary risk classification with a
  strict schema, hard timeout and fail-closed verdicts.
* :mod:`dream.security.history` — the durable, append-only approval log.
* :mod:`dream.security.engine` — L2 mode orchestration around the floor.

P6 adds the agentic layer (L9) on top, hardening the surfaces that
research, data Q&A, workspace/agent modes and the provider hubs opened:

* :mod:`dream.security.agentcode` — sandbox-only execution policy for
  model-generated code; the host never runs it.
* :mod:`dream.security.codegrounding` — data-as-data framing so dataset
  rows and tool output cannot steer code generation.
* :mod:`dream.security.planpolicy` — plan-approval gating, degraded
  autonomous grants, approval-attempt limiting.
* :mod:`dream.security.authenticity` — artifact seals and ungrounded-claim
  rejection over :mod:`dream.provenance`.
* :mod:`dream.security.providergateway` — least-privilege gateway tokens
  and bounded, non-exfiltrating runtime probes.
"""

from dream.security.agentcode import (
    ALLOWED_IMPORTS,
    AgentCodeRefusal,
    AgentCodeResult,
    SandboxPolicy,
    confine_path,
    preflight_code,
    run_agent_code,
)
from dream.security.assessor import ASSESS_TIMEOUT_SECONDS, Assessment, assess, pattern_assess
from dream.security.authenticity import (
    ArtifactSeal,
    ClaimReport,
    RunFingerprint,
    seal_artifact,
    verify_artifact,
    verify_claims,
)
from dream.security.blocklist import RULES, BlockMatch, BlockRule, ScanText, floor_refusal, scan
from dream.security.codegrounding import (
    GroundingReport,
    as_code_literal,
    as_parameter_block,
    frame_as_data,
    ground_rows,
    guard_codegen_context,
    scan_data_payload,
)
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
from dream.security.planpolicy import (
    DEGRADED_GRANTS,
    EXPENSIVE_ACTIONS,
    ApprovalAttemptLimiter,
    PlanApproval,
    PlanGate,
    PlanRefusal,
    authorize_tool,
    degraded_grants,
    plan_digest,
)
from dream.security.providergateway import (
    GATEWAY_SCOPES,
    GatewayPolicyError,
    GatewayRefusal,
    ProbeResult,
    ScopedToken,
    ScopedTokenStore,
    mint_token,
    probe_runtime,
    redact_headers,
    safe_snapshot,
    tool_enabled,
)

__all__ = [
    "ALLOWED_IMPORTS",
    "APPROVAL_DB_ENV",
    "ASSESS_TIMEOUT_SECONDS",
    "AgentCodeRefusal",
    "AgentCodeResult",
    "ApprovalAttemptLimiter",
    "ApprovalHistory",
    "ApprovalStoreError",
    "ArtifactSeal",
    "Assessment",
    "BlockMatch",
    "BlockRule",
    "CONTEXT_MODES",
    "ClaimReport",
    "DEFAULT_APPROVAL_DB",
    "DEGRADED_GRANTS",
    "Decision",
    "EXPENSIVE_ACTIONS",
    "GATEWAY_SCOPES",
    "GatewayPolicyError",
    "GatewayRefusal",
    "GroundingReport",
    "MODES",
    "PlanApproval",
    "PlanGate",
    "PlanRefusal",
    "ProbeResult",
    "RULES",
    "RunFingerprint",
    "SHELL_COMMAND_TOOLS",
    "SandboxPolicy",
    "ScanText",
    "ScopedToken",
    "ScopedTokenStore",
    "SecurityEngine",
    "as_code_literal",
    "as_parameter_block",
    "assess",
    "authorize_tool",
    "confine_path",
    "default_engine",
    "degraded_grants",
    "floor_refusal",
    "frame_as_data",
    "ground_rows",
    "guard_codegen_context",
    "mint_token",
    "pattern_assess",
    "plan_digest",
    "preflight_code",
    "probe_runtime",
    "redact_headers",
    "reset_default_engine",
    "run_agent_code",
    "safe_snapshot",
    "scan",
    "scan_data_payload",
    "seal_artifact",
    "tool_enabled",
    "verify_artifact",
    "verify_claims",
]
