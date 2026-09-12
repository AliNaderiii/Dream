"""Master RBAC & Token Quota Gateway Engine for Dream Multi-Tenant Architecture."""

from __future__ import annotations

import json
import uuid
from typing import Any

from dream.rbac.permissions import check_user_permission
from dream.rbac.quota import QuotaManager
from dream.rbac.types import (
    AccountStatus,
    AuditEntry,
    QuotaConfig,
    Role,
    Tenant,
    TenantTier,
    User,
)


class RBACEngine:
    """Master governance gateway managing tenants, users, access verification, and audit logs."""

    def __init__(self) -> None:
        self._tenants: dict[str, Tenant] = {}
        self._users: dict[str, User] = {}
        self._audit_log: list[AuditEntry] = []
        self._init_defaults()

    def _init_defaults(self) -> None:
        """Seed default master organization tenant and root admin user."""
        default_tenant = Tenant(
            tenant_id="tenant-root",
            name="سازمان پیش‌فرض Dream",
            tier=TenantTier.ENTERPRISE,
            quota=QuotaConfig(
                monthly_token_budget=10_000_000,
                daily_token_budget=1_000_000,
                requests_per_minute=200,
            ),
        )
        self._tenants[default_tenant.tenant_id] = default_tenant

        root_user = User(
            user_id="user-root",
            tenant_id=default_tenant.tenant_id,
            username="admin",
            roles=[Role.SUPER_ADMIN],
        )
        self._users[root_user.user_id] = root_user

    def create_tenant(
        self,
        tenant_id: str,
        name: str,
        tier: TenantTier = TenantTier.PRO,
        monthly_token_budget: int = 1_000_000,
        daily_token_budget: int = 100_000,
        requests_per_minute: int = 60,
    ) -> Tenant:
        """Register a new enterprise tenant with customized quota parameters."""
        quota = QuotaConfig(
            monthly_token_budget=monthly_token_budget,
            daily_token_budget=daily_token_budget,
            requests_per_minute=requests_per_minute,
        )
        tenant = Tenant(
            tenant_id=tenant_id,
            name=name,
            tier=tier,
            quota=quota,
        )
        self._tenants[tenant_id] = tenant
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Retrieve tenant by ID."""
        return self._tenants.get(tenant_id)

    def list_tenants(self) -> list[dict[str, Any]]:
        """Return list of all registered tenants."""
        return [t.to_dict() for t in self._tenants.values()]

    def create_user(
        self,
        user_id: str,
        tenant_id: str,
        username: str,
        roles: list[Role] | None = None,
        custom_permissions: set[str] | None = None,
    ) -> User:
        """Register a new user identity assigned to a specific tenant."""
        if tenant_id not in self._tenants:
            raise ValueError(f"سازمان با شناسه `{tenant_id}` یافت نشد.")

        user = User(
            user_id=user_id,
            tenant_id=tenant_id,
            username=username,
            roles=roles or [Role.DEVELOPER],
            custom_permissions=custom_permissions or set(),
        )
        self._users[user_id] = user
        return user

    def get_user(self, user_id: str) -> User | None:
        """Retrieve user by ID."""
        return self._users.get(user_id)

    def list_users(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """Return list of users, optionally filtered by tenant."""
        users = self._users.values()
        if tenant_id:
            users = [u for u in users if u.tenant_id == tenant_id]
        return [u.to_dict() for u in users]

    def verify_access(
        self,
        tenant_id: str,
        user_id: str,
        required_permission: str,
        resource: str = "default",
        estimated_tokens: int = 0,
    ) -> tuple[bool, str]:
        """Perform comprehensive authorization, status check, and quota validation.

        Returns:
            Tuple of (is_granted, reason_fa)
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            reason = f"سازمان `{tenant_id}` یافت نشد."
            self._record_audit(tenant_id, user_id, required_permission, resource, False, reason)
            return False, reason

        if tenant.status != AccountStatus.ACTIVE:
            reason = f"سازمان `{tenant_id}` فعال نیست (وضعیت: {tenant.status.value})."
            self._record_audit(tenant_id, user_id, required_permission, resource, False, reason)
            return False, reason

        user = self.get_user(user_id)
        if not user:
            reason = f"کاربر `{user_id}` یافت نشد."
            self._record_audit(tenant_id, user_id, required_permission, resource, False, reason)
            return False, reason

        if user.tenant_id != tenant_id:
            reason = f"کاربر `{user_id}` متعلق به سازمان `{tenant_id}` نیست."
            self._record_audit(tenant_id, user_id, required_permission, resource, False, reason)
            return False, reason

        # 1. RBAC Permission Check
        perm_ok, perm_reason = check_user_permission(user, required_permission)
        if not perm_ok:
            self._record_audit(
                tenant_id, user_id, required_permission, resource, False, perm_reason
            )
            return False, perm_reason

        # 2. Rate Limit Check
        rate_ok, rate_reason = QuotaManager.check_rate_limit(tenant, estimated_tokens)
        if not rate_ok:
            self._record_audit(
                tenant_id, user_id, required_permission, resource, False, rate_reason
            )
            return False, rate_reason

        # 3. Token Budget Check
        budget_ok, budget_reason = QuotaManager.check_token_budget(tenant, estimated_tokens)
        if not budget_ok:
            self._record_audit(
                tenant_id, user_id, required_permission, resource, False, budget_reason
            )
            return False, budget_reason

        # Access Granted
        success_msg = f"دسترسی مجاز: {perm_reason}"
        self._record_audit(tenant_id, user_id, required_permission, resource, True, success_msg)
        return True, success_msg

    def record_usage(
        self,
        tenant_id: str,
        tokens: int,
        is_tool_call: bool = False,
    ) -> dict[str, Any]:
        """Record token consumption for a tenant."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"success": False, "error": f"Tenant '{tenant_id}' not found."}
        res = QuotaManager.record_consumption(tenant, tokens, is_tool_call=is_tool_call)
        return {"success": True, **res}

    def _record_audit(
        self,
        tenant_id: str,
        user_id: str,
        action: str,
        resource: str,
        granted: bool,
        reason_fa: str,
    ) -> AuditEntry:
        """Create and append an immutable audit log entry."""
        entry = AuditEntry(
            audit_id=f"audit-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            granted=granted,
            reason_fa=reason_fa,
        )
        self._audit_log.append(entry)
        return entry

    def get_audit_log(
        self,
        tenant_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return recent audit entries."""
        logs = self._audit_log
        if tenant_id:
            logs = [e for e in logs if e.tenant_id == tenant_id]
        return [e.to_dict() for e in logs[-limit:]]

    def export_audit_markdown(self, tenant_id: str | None = None) -> str:
        """Format audit events into Markdown report."""
        logs = self._audit_log
        if tenant_id:
            logs = [e for e in logs if e.tenant_id == tenant_id]

        lines = [
            "# 🛡️ گزارش لاگ ممیزی و دسترسی سازمانی (RBAC & Quota Audit)",
            f"- **تعداد کل رخدادها**: `{len(logs)}`",
            f"- **فیلتر سازمان**: `{tenant_id or 'تمام سازمان‌ها'}`",
            "",
            "| شناسه | کاربر | اکشن | منبع | وضعیت | علت |",
            "| :--- | :--- | :--- | :--- | :---: | :--- |",
        ]

        if not logs:
            lines.append("| - | - | - | - | - | _هیچ رخدادی ثبت نشده است_ |")
        else:
            for entry in logs[-20:]:
                status_icon = "✅ مجاز" if entry.granted else "❌ رد شده"
                lines.append(
                    f"| `{entry.audit_id}` | `{entry.user_id}` | `{entry.action}` | "
                    f"`{entry.resource}` | {status_icon} | {entry.reason_fa} |"
                )

        return "\n".join(lines)

    def export_json(self) -> str:
        """Export state to JSON string."""
        data = {
            "tenants": self.list_tenants(),
            "users": self.list_users(),
            "audit_count": len(self._audit_log),
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def reset(self) -> None:
        """Reset all tenants, users, and logs to default seed state."""
        self._tenants.clear()
        self._users.clear()
        self._audit_log.clear()
        self._init_defaults()


# Global Singleton
_GLOBAL_RBAC_ENGINE: RBACEngine | None = None


def get_rbac_engine() -> RBACEngine:
    """Retrieve global singleton instance of RBACEngine."""
    global _GLOBAL_RBAC_ENGINE
    if _GLOBAL_RBAC_ENGINE is None:
        _GLOBAL_RBAC_ENGINE = RBACEngine()
    return _GLOBAL_RBAC_ENGINE
