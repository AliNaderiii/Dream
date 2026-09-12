"""Role-to-Permission mapping and wildcard policy evaluation engine."""

from __future__ import annotations

import fnmatch
from collections.abc import Collection

from dream.rbac.types import Permission, Role, User

ROLE_PERMISSIONS: dict[Role, set[str]] = {
    Role.SUPER_ADMIN: {
        Permission.ALL.value,
    },
    Role.ADMIN: {
        Permission.TOOL_EXECUTE.value,
        Permission.CODE_SANDBOX_RUN.value,
        Permission.DATABASE_QUERY.value,
        Permission.FINANCIAL_EXECUTE.value,
        Permission.MEMORY_READ.value,
        Permission.MEMORY_WRITE.value,
        Permission.MEMORY_PURGE.value,
        Permission.KNOWLEDGE_READ.value,
        Permission.KNOWLEDGE_WRITE.value,
        Permission.RESEARCH_DEEP_RUN.value,
        Permission.WORKFLOW_READ.value,
        Permission.WORKFLOW_EXECUTE.value,
        Permission.WORKFLOW_ADMIN.value,
        Permission.RBAC_MANAGE.value,
        Permission.QUOTA_MANAGE.value,
        Permission.AUDIT_VIEW.value,
    },
    Role.DEVELOPER: {
        Permission.TOOL_EXECUTE.value,
        Permission.CODE_SANDBOX_RUN.value,
        Permission.DATABASE_QUERY.value,
        Permission.MEMORY_READ.value,
        Permission.MEMORY_WRITE.value,
        Permission.KNOWLEDGE_READ.value,
        Permission.KNOWLEDGE_WRITE.value,
        Permission.RESEARCH_DEEP_RUN.value,
        Permission.WORKFLOW_READ.value,
        Permission.WORKFLOW_EXECUTE.value,
    },
    Role.ANALYST: {
        Permission.DATABASE_QUERY.value,
        Permission.MEMORY_READ.value,
        Permission.KNOWLEDGE_READ.value,
        Permission.RESEARCH_DEEP_RUN.value,
        Permission.WORKFLOW_READ.value,
        Permission.AUDIT_VIEW.value,
    },
    Role.VIEWER: {
        Permission.MEMORY_READ.value,
        Permission.KNOWLEDGE_READ.value,
        Permission.WORKFLOW_READ.value,
        Permission.AUDIT_VIEW.value,
    },
    Role.GUEST: {
        Permission.MEMORY_READ.value,
        Permission.KNOWLEDGE_READ.value,
    },
    Role.CUSTOM: set(),
}


def match_permission(pattern: str, target_permission: str) -> bool:
    """Check if target permission matches pattern with wildcard support."""
    if pattern == "*" or pattern == target_permission:
        return True
    return fnmatch.fnmatch(target_permission, pattern)


def get_effective_permissions(user: User) -> set[str]:
    """Calculate the aggregated set of permissions for a user across all roles and overrides."""
    permissions: set[str] = set()
    for role in user.roles:
        role_perms = ROLE_PERMISSIONS.get(role, set())
        permissions.update(role_perms)

    # Add explicit custom permissions
    permissions.update(user.custom_permissions)
    return permissions


def check_user_permission(
    user: User,
    required_permission: str,
    explicit_allowed_roles: Collection[Role] | None = None,
) -> tuple[bool, str]:
    """Evaluate whether user is authorized for required permission.

    Returns:
        Tuple of (is_granted, reason_fa)
    """
    if user.status.value != "active":
        return False, f"حساب کاربری `{user.user_id}` غیرفعال یا معلق است."

    if explicit_allowed_roles:
        if any(r in explicit_allowed_roles for r in user.roles):
            return True, "دسترسی مجاز بر اساس نقش مستقیم."

    effective = get_effective_permissions(user)
    if Permission.ALL.value in effective:
        return True, "دسترسی کامل (Super Admin) مجاز است."

    for pattern in effective:
        if match_permission(pattern, required_permission):
            return True, f"دسترسی مجاز با الگوی مجوز `{pattern}`."

    return False, f"کاربر `{user.username}` فاقد مجوز `{required_permission}` است."
