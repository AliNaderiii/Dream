"""Enterprise Multi-Tenant RBAC & Token Quota Gateway Subsystem for Dream."""

from __future__ import annotations

from dream.rbac.engine import RBACEngine, get_rbac_engine
from dream.rbac.permissions import (
    ROLE_PERMISSIONS,
    check_user_permission,
    get_effective_permissions,
    match_permission,
)
from dream.rbac.quota import QuotaManager
from dream.rbac.slash import handle_rbac_command
from dream.rbac.tools import (
    get_global_rbac_engine,
    get_rbac_tools,
    rbac_create_tenant,
    rbac_create_user,
    rbac_export_audit_log,
    rbac_get_quota_status,
    rbac_record_usage,
    rbac_reset,
    rbac_verify_access,
    reset_global_rbac_engine,
)
from dream.rbac.types import (
    AccountStatus,
    AuditEntry,
    Permission,
    QuotaConfig,
    QuotaUsage,
    Role,
    Tenant,
    TenantTier,
    User,
)

__all__ = [
    "ROLE_PERMISSIONS",
    "AccountStatus",
    "AuditEntry",
    "Permission",
    "QuotaConfig",
    "QuotaManager",
    "QuotaUsage",
    "RBACEngine",
    "Role",
    "Tenant",
    "TenantTier",
    "User",
    "check_user_permission",
    "get_effective_permissions",
    "get_global_rbac_engine",
    "get_rbac_engine",
    "get_rbac_tools",
    "handle_rbac_command",
    "match_permission",
    "rbac_create_tenant",
    "rbac_create_user",
    "rbac_export_audit_log",
    "rbac_get_quota_status",
    "rbac_record_usage",
    "rbac_reset",
    "rbac_verify_access",
    "reset_global_rbac_engine",
]
