"""Data models and type definitions for Enterprise Multi-Tenant RBAC & Quotas."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TenantTier(str, Enum):
    """Subscription tiers for multi-tenant organizations."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class AccountStatus(str, Enum):
    """Account and tenant activation status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class Role(str, Enum):
    """Standard predefined roles in RBAC hierarchy."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    DEVELOPER = "developer"
    ANALYST = "analyst"
    VIEWER = "viewer"
    GUEST = "guest"
    CUSTOM = "custom"


class Permission(str, Enum):
    """Granular action permissions across Dream subsystems."""

    # All permissions wildcard
    ALL = "*"

    # Tools & Execution
    TOOL_EXECUTE = "tool:execute"
    CODE_SANDBOX_RUN = "sandbox:code_run"
    SYSTEM_SHELL_RUN = "system:shell_run"
    DATABASE_QUERY = "db:query"
    FINANCIAL_EXECUTE = "finance:execute"

    # Memory & Context
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_PURGE = "memory:purge"

    # Knowledge & Research
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_WRITE = "knowledge:write"
    RESEARCH_DEEP_RUN = "research:deep_run"

    # Workflow & Orchestration
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_EXECUTE = "workflow:execute"
    WORKFLOW_ADMIN = "workflow:admin"

    # Admin & Governance
    RBAC_MANAGE = "rbac:manage"
    QUOTA_MANAGE = "quota:manage"
    AUDIT_VIEW = "audit:view"


@dataclass
class QuotaConfig:
    """Token budget and rate limiting limits for a tenant or user."""

    monthly_token_budget: int = 1_000_000
    daily_token_budget: int = 100_000
    requests_per_minute: int = 60
    tokens_per_minute: int = 50_000
    concurrent_sessions_limit: int = 10
    max_context_window: int = 128_000


@dataclass
class QuotaUsage:
    """Real-time token usage and request counters."""

    monthly_tokens_used: int = 0
    daily_tokens_used: int = 0
    total_requests: int = 0
    tool_calls_count: int = 0
    last_request_timestamp: float = field(default_factory=time.time)
    minute_request_timestamps: list[float] = field(default_factory=list)
    minute_token_counts: list[tuple[float, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize usage to dictionary."""
        return {
            "monthly_tokens_used": self.monthly_tokens_used,
            "daily_tokens_used": self.daily_tokens_used,
            "total_requests": self.total_requests,
            "tool_calls_count": self.tool_calls_count,
            "last_request_timestamp": self.last_request_timestamp,
        }


@dataclass
class Tenant:
    """Organization tenant in a multi-tenant enterprise deployment."""

    tenant_id: str
    name: str
    tier: TenantTier = TenantTier.PRO
    status: AccountStatus = AccountStatus.ACTIVE
    quota: QuotaConfig = field(default_factory=QuotaConfig)
    usage: QuotaUsage = field(default_factory=QuotaUsage)
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize tenant to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "name": self.name,
            "tier": self.tier.value,
            "status": self.status.value,
            "quota": {
                "monthly_token_budget": self.quota.monthly_token_budget,
                "daily_token_budget": self.quota.daily_token_budget,
                "requests_per_minute": self.quota.requests_per_minute,
            },
            "usage": self.usage.to_dict(),
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class User:
    """Individual identity within a tenant."""

    user_id: str
    tenant_id: str
    username: str
    roles: list[Role] = field(default_factory=lambda: [Role.DEVELOPER])
    custom_permissions: set[str] = field(default_factory=set)
    status: AccountStatus = AccountStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize user to dictionary."""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "username": self.username,
            "roles": [r.value for r in self.roles],
            "custom_permissions": sorted(self.custom_permissions),
            "status": self.status.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class AuditEntry:
    """Immutable audit entry recording an access or governance event."""

    audit_id: str
    tenant_id: str
    user_id: str
    action: str
    resource: str
    granted: bool
    reason_fa: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize audit entry to dictionary."""
        return {
            "audit_id": self.audit_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "action": self.action,
            "resource": self.resource,
            "granted": self.granted,
            "reason_fa": self.reason_fa,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
