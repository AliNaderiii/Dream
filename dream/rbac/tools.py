"""LLM agent tools and singleton managers for Enterprise RBAC & Quotas."""

from __future__ import annotations

import logging
from typing import Any

from dream.rbac.engine import RBACEngine, get_rbac_engine
from dream.rbac.types import Role, TenantTier

logger = logging.getLogger(__name__)

_GLOBAL_RBAC_ENGINE: RBACEngine | None = None


def get_global_rbac_engine() -> RBACEngine:
    """Retrieve or initialize singleton RBACEngine."""
    global _GLOBAL_RBAC_ENGINE
    if _GLOBAL_RBAC_ENGINE is None:
        _GLOBAL_RBAC_ENGINE = get_rbac_engine()
    return _GLOBAL_RBAC_ENGINE


def reset_global_rbac_engine() -> None:
    """Reset global RBACEngine instance for test isolation."""
    global _GLOBAL_RBAC_ENGINE
    if _GLOBAL_RBAC_ENGINE is not None:
        _GLOBAL_RBAC_ENGINE.reset()
    _GLOBAL_RBAC_ENGINE = None


def rbac_create_tenant(
    tenant_id: str,
    name: str,
    tier: str = "pro",
    monthly_budget: int = 1_000_000,
    daily_budget: int = 100_000,
    rpm: int = 60,
) -> dict[str, Any]:
    """Register a new enterprise tenant organization with token budget.

    Args:
        tenant_id: Unique organization identifier.
        name: Name of the organization.
        tier: Subscription tier ('free', 'pro', 'enterprise').
        monthly_budget: Maximum tokens allowed per month.
        daily_budget: Maximum tokens allowed per day.
        rpm: Requests allowed per minute.
    """
    engine = get_global_rbac_engine()
    try:
        tier_enum = TenantTier(tier.lower())
    except ValueError:
        tier_enum = TenantTier.PRO

    tenant = engine.create_tenant(
        tenant_id=tenant_id,
        name=name,
        tier=tier_enum,
        monthly_token_budget=monthly_budget,
        daily_token_budget=daily_budget,
        requests_per_minute=rpm,
    )
    return {
        "success": True,
        "tenant": tenant.to_dict(),
        "summary_fa": f"سازمان `{name}` با سهمیه ماهانه {monthly_budget:,} توکن ایجاد شد.",
    }


def rbac_create_user(
    user_id: str,
    tenant_id: str,
    username: str,
    roles: list[str] | None = None,
    custom_permissions: list[str] | None = None,
) -> dict[str, Any]:
    """Register a new user identity under an organization with specific roles.

    Args:
        user_id: Unique user identifier.
        tenant_id: Organization ID the user belongs to.
        username: Display username.
        roles: List of roles (e.g. ['developer', 'analyst']).
        custom_permissions: Optional list of granular permission strings.
    """
    engine = get_global_rbac_engine()
    role_enums: list[Role] = []
    for r in roles or ["developer"]:
        try:
            role_enums.append(Role(r.lower()))
        except ValueError:
            role_enums.append(Role.DEVELOPER)

    try:
        user = engine.create_user(
            user_id=user_id,
            tenant_id=tenant_id,
            username=username,
            roles=role_enums,
            custom_permissions=set(custom_permissions or []),
        )
        return {
            "success": True,
            "user": user.to_dict(),
            "summary_fa": f"کاربر `{username}` در سازمان `{tenant_id}` با نقش‌های {roles} ثبت شد.",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def rbac_verify_access(
    tenant_id: str,
    user_id: str,
    permission: str,
    resource: str = "default",
    estimated_tokens: int = 0,
) -> dict[str, Any]:
    """Verify if a user has permission to execute an action and if quotas permit.

    Args:
        tenant_id: Organization ID.
        user_id: User ID requesting access.
        permission: Permission string (e.g. 'tool:execute', 'sandbox:code_run').
        resource: Target resource or tool name.
        estimated_tokens: Anticipated token consumption.
    """
    engine = get_global_rbac_engine()
    granted, reason = engine.verify_access(
        tenant_id=tenant_id,
        user_id=user_id,
        required_permission=permission,
        resource=resource,
        estimated_tokens=estimated_tokens,
    )
    return {
        "success": True,
        "granted": granted,
        "reason_fa": reason,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "permission": permission,
    }


def rbac_record_usage(
    tenant_id: str,
    tokens: int,
    is_tool_call: bool = False,
) -> dict[str, Any]:
    """Record consumed tokens and update quota counters for a tenant.

    Args:
        tenant_id: Organization ID.
        tokens: Number of tokens consumed.
        is_tool_call: Whether this was a tool execution.
    """
    engine = get_global_rbac_engine()
    return engine.record_usage(tenant_id, tokens, is_tool_call=is_tool_call)


def rbac_get_quota_status(tenant_id: str) -> dict[str, Any]:
    """Retrieve token balance, daily and monthly usage for an organization.

    Args:
        tenant_id: Organization ID.
    """
    engine = get_global_rbac_engine()
    tenant = engine.get_tenant(tenant_id)
    if not tenant:
        return {"success": False, "error": f"سازمان `{tenant_id}` یافت نشد."}
    return {
        "success": True,
        "tenant_id": tenant_id,
        "name": tenant.name,
        "tier": tenant.tier.value,
        "status": tenant.status.value,
        "quota": {
            "monthly_budget": tenant.quota.monthly_token_budget,
            "daily_budget": tenant.quota.daily_token_budget,
            "rpm_limit": tenant.quota.requests_per_minute,
        },
        "usage": tenant.usage.to_dict(),
        "remaining_monthly": max(
            0, tenant.quota.monthly_token_budget - tenant.usage.monthly_tokens_used
        ),
        "remaining_daily": max(
            0, tenant.quota.daily_token_budget - tenant.usage.daily_tokens_used
        ),
    }


def rbac_export_audit_log(
    tenant_id: str = "",
    format: str = "markdown",
) -> dict[str, Any]:
    """Export security and access audit logs for an organization.

    Args:
        tenant_id: Optional organization filter.
        format: Output format ('markdown' or 'json').
    """
    engine = get_global_rbac_engine()
    tid = tenant_id if tenant_id else None
    if format.lower() == "json":
        return {"success": True, "format": "json", "logs": engine.get_audit_log(tid)}
    return {
        "success": True,
        "format": "markdown",
        "audit_markdown": engine.export_audit_markdown(tid),
    }


def rbac_reset() -> dict[str, Any]:
    """Reset RBAC engine to initial seed state."""
    reset_global_rbac_engine()
    return {"success": True, "message_fa": "موتور مدیریت دسترسی و سهمیه با موفقیت بازنشانی شد."}


def get_rbac_tools() -> list[dict[str, Any]]:
    """Return tool manifests for LLM registration."""
    return [
        {
            "name": "rbac_create_tenant",
            "description": "Create a new enterprise tenant organization with token quotas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenant_id": {"type": "string"},
                    "name": {"type": "string"},
                    "tier": {"type": "string", "enum": ["free", "pro", "enterprise"]},
                    "monthly_budget": {"type": "integer", "default": 1000000},
                    "daily_budget": {"type": "integer", "default": 100000},
                    "rpm": {"type": "integer", "default": 60},
                },
                "required": ["tenant_id", "name"],
            },
            "handler": rbac_create_tenant,
        },
        {
            "name": "rbac_create_user",
            "description": "Register a new user under a tenant with specific RBAC roles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "tenant_id": {"type": "string"},
                    "username": {"type": "string"},
                    "roles": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["user_id", "tenant_id", "username"],
            },
            "handler": rbac_create_user,
        },
        {
            "name": "rbac_verify_access",
            "description": "Check if a user is authorized for a permission and has quota.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenant_id": {"type": "string"},
                    "user_id": {"type": "string"},
                    "permission": {"type": "string"},
                    "resource": {"type": "string", "default": "default"},
                    "estimated_tokens": {"type": "integer", "default": 0},
                },
                "required": ["tenant_id", "user_id", "permission"],
            },
            "handler": rbac_verify_access,
        },
        {
            "name": "rbac_record_usage",
            "description": "Record token consumption and tool invocations for a tenant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenant_id": {"type": "string"},
                    "tokens": {"type": "integer"},
                    "is_tool_call": {"type": "boolean", "default": False},
                },
                "required": ["tenant_id", "tokens"],
            },
            "handler": rbac_record_usage,
        },
        {
            "name": "rbac_get_quota_status",
            "description": "Inspect remaining token balance and quota usage for a tenant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenant_id": {"type": "string"},
                },
                "required": ["tenant_id"],
            },
            "handler": rbac_get_quota_status,
        },
        {
            "name": "rbac_export_audit_log",
            "description": "Export the immutable security audit log of access events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tenant_id": {"type": "string", "default": ""},
                    "format": {
                        "type": "string",
                        "enum": ["markdown", "json"],
                        "default": "markdown",
                    },
                },
            },
            "handler": rbac_export_audit_log,
        },
    ]
