"""Comprehensive tests for Enterprise Multi-Tenant RBAC & Token Quota Gateway."""

from __future__ import annotations

import pytest

from dream.rbac.engine import RBACEngine
from dream.rbac.permissions import (
    check_user_permission,
    get_effective_permissions,
    match_permission,
)
from dream.rbac.quota import QuotaManager
from dream.rbac.slash import handle_rbac_command
from dream.rbac.tools import (
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
    Permission,
    QuotaConfig,
    Role,
    Tenant,
    TenantTier,
    User,
)
from dream.tools.toolsets import get_toolset


@pytest.fixture(autouse=True)
def cleanup_rbac() -> None:
    reset_global_rbac_engine()
    yield
    reset_global_rbac_engine()


def test_toolset_includes_rbac() -> None:
    """Verify rbac toolset is registered in BUILTIN_TOOLSETS."""
    ts = get_toolset("rbac")
    assert ts is not None
    assert ts.name == "rbac"
    assert "rbac_create_tenant" in ts.tools
    assert "rbac_verify_access" in ts.tools
    assert "rbac_get_quota_status" in ts.tools


def test_permission_wildcard_matching() -> None:
    """Test permission pattern matching and wildcard logic."""
    assert match_permission("*", "tool:execute")
    assert match_permission("tool:*", "tool:execute")
    assert match_permission("memory:*", "memory:write")
    assert not match_permission("memory:*", "tool:execute")
    assert match_permission("db:query", "db:query")


def test_user_effective_permissions() -> None:
    """Test role resolution and custom permission overrides."""
    user = User(
        user_id="u1",
        tenant_id="t1",
        username="dev1",
        roles=[Role.DEVELOPER],
        custom_permissions={"custom:feature"},
    )
    perms = get_effective_permissions(user)
    assert Permission.TOOL_EXECUTE.value in perms
    assert Permission.CODE_SANDBOX_RUN.value in perms
    assert "custom:feature" in perms
    assert Permission.FINANCIAL_EXECUTE.value not in perms

    # Check permission evaluation
    ok, reason = check_user_permission(user, Permission.TOOL_EXECUTE.value)
    assert ok is True

    # Denied permission
    nok, reason_nok = check_user_permission(user, Permission.FINANCIAL_EXECUTE.value)
    assert nok is False
    assert "فاقد مجوز" in reason_nok


def test_quota_rate_limiting_and_budgets() -> None:
    """Test sliding window rate limiting and token budget tracking."""
    tenant = Tenant(
        tenant_id="t_test",
        name="آزمایشی",
        tier=TenantTier.PRO,
        quota=QuotaConfig(
            monthly_token_budget=10_000,
            daily_token_budget=1_000,
            requests_per_minute=2,
            tokens_per_minute=500,
        ),
    )

    # 1. First request allowed
    r1, _ = QuotaManager.check_rate_limit(tenant, estimated_tokens=100)
    assert r1 is True
    QuotaManager.record_consumption(tenant, tokens=100)

    # 2. Second request allowed
    r2, _ = QuotaManager.check_rate_limit(tenant, estimated_tokens=100)
    assert r2 is True
    QuotaManager.record_consumption(tenant, tokens=100)

    # 3. Third request within same minute blocked by RPM
    r3, reason_rpm = QuotaManager.check_rate_limit(tenant, estimated_tokens=100)
    assert r3 is False
    assert "RPM" in reason_rpm

    # 4. Check budget overconsumption
    b_ok, _ = QuotaManager.check_token_budget(tenant, requested_tokens=500)
    assert b_ok is True

    b_fail, reason_b = QuotaManager.check_token_budget(tenant, requested_tokens=2_000)
    assert b_fail is False
    assert "سهمیه روزانه" in reason_b


def test_rbac_engine_lifecycle_and_audit() -> None:
    """Test RBACEngine tenant, user, access verification, and audit logs."""
    engine = RBACEngine()

    # Create tenant
    tenant = engine.create_tenant(
        tenant_id="acme_corp",
        name="شرکت اکمه",
        tier=TenantTier.ENTERPRISE,
        monthly_token_budget=50_000,
        daily_token_budget=5_000,
    )
    assert tenant.tenant_id == "acme_corp"

    # Create developer user
    user = engine.create_user(
        user_id="dev_sara",
        tenant_id="acme_corp",
        username="sara",
        roles=[Role.DEVELOPER],
    )
    assert user.username == "sara"

    # Verify granted action
    ok_grant, _ = engine.verify_access(
        tenant_id="acme_corp",
        user_id="dev_sara",
        required_permission=Permission.CODE_SANDBOX_RUN.value,
        resource="python_repl",
        estimated_tokens=50,
    )
    assert ok_grant is True

    # Verify denied action (developer trying to manage RBAC)
    nok_grant, _ = engine.verify_access(
        tenant_id="acme_corp",
        user_id="dev_sara",
        required_permission=Permission.RBAC_MANAGE.value,
    )
    assert nok_grant is False

    # Suspended tenant test
    tenant.status = AccountStatus.SUSPENDED
    nok_susp, reason_susp = engine.verify_access(
        tenant_id="acme_corp",
        user_id="dev_sara",
        required_permission=Permission.CODE_SANDBOX_RUN.value,
    )
    assert nok_susp is False
    assert "فعال نیست" in reason_susp

    # Check audit log export
    logs = engine.get_audit_log(tenant_id="acme_corp")
    assert len(logs) >= 3
    md_report = engine.export_audit_markdown("acme_corp")
    assert "گزارش لاگ ممیزی" in md_report


def test_rbac_tools_and_slash_commands() -> None:
    """Test RBAC LLM agent tools and slash command dispatcher."""
    tools = get_rbac_tools()
    assert len(tools) >= 6

    # 1. Tool: create tenant
    res_t = rbac_create_tenant(
        tenant_id="org_fin",
        name="سازمان مالی",
        tier="enterprise",
        monthly_budget=200_000,
    )
    assert res_t["success"] is True

    # 2. Tool: create user
    res_u = rbac_create_user(
        user_id="user_ali",
        tenant_id="org_fin",
        username="ali",
        roles=["analyst"],
    )
    assert res_u["success"] is True

    # 3. Tool: verify access
    res_v = rbac_verify_access(
        tenant_id="org_fin",
        user_id="user_ali",
        permission="knowledge:read",
    )
    assert res_v["success"] is True
    assert res_v["granted"] is True

    # 4. Tool: record usage
    res_use = rbac_record_usage("org_fin", tokens=500, is_tool_call=True)
    assert res_use["success"] is True

    # 5. Tool: quota status
    res_q = rbac_get_quota_status("org_fin")
    assert res_q["success"] is True
    assert res_q["remaining_monthly"] == 199_500

    # 6. Tool: audit log
    res_a = rbac_export_audit_log("org_fin", format="markdown")
    assert "گزارش لاگ ممیزی" in res_a["audit_markdown"]

    # 7. Slash command help
    s_help = handle_rbac_command("")
    assert "راهنمای دستورات مدیریت دسترسی" in s_help

    # Slash: tenant list
    s_tl = handle_rbac_command("tenant list")
    assert "سازمان‌های ثبت‌شده" in s_tl

    # Slash: user list
    s_ul = handle_rbac_command("user list org_fin")
    assert "فهرست کاربران" in s_ul

    # Slash: check
    s_chk = handle_rbac_command("check org_fin user_ali knowledge:read")
    assert "مجاز" in s_chk

    # Slash: quota
    s_quota = handle_rbac_command("quota org_fin")
    assert "وضعیت سهمیه" in s_quota

    # Slash: reset
    s_reset = handle_rbac_command("reset")
    assert "با موفقیت ریست شد" in s_reset

    # Tool reset
    t_reset = rbac_reset()
    assert t_reset["success"] is True
