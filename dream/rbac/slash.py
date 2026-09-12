"""Slash command dispatcher for the Enterprise RBAC & Quotas subsystem."""

from __future__ import annotations

import shlex

from dream.rbac.engine import get_rbac_engine
from dream.rbac.types import Role, TenantTier


def handle_rbac_command(args_str: str) -> str:
    """Handle /rbac slash commands.

    Usage:
        /rbac tenant create <id> <name> [monthly_budget]
        /rbac tenant list
        /rbac user create <user_id> <tenant_id> <username> [role]
        /rbac user list [tenant_id]
        /rbac check <tenant_id> <user_id> <permission>
        /rbac quota <tenant_id>
        /rbac audit [tenant_id]
        /rbac reset
    """
    if not args_str.strip():
        return (
            "🛡️ **راهنمای دستورات مدیریت دسترسی و سهمیه سازمانی (RBAC & Quotas):**\n\n"
            "- `/rbac tenant create <id> <name> [monthly_budget]` : ثبت سازمان جدید\n"
            "- `/rbac tenant list` : مشاهده فهرست تمام سازمان‌ها\n"
            "- `/rbac user create <user_id> <tenant_id> <username> [role]` : ثبت کاربر جدید\n"
            "- `/rbac user list [tenant_id]` : مشاهده کاربران یک سازمان\n"
            "- `/rbac check <tenant_id> <user_id> <permission>` : اعتبارسنجی سطح دسترسی کاربر\n"
            "- `/rbac quota <tenant_id>` : استعلام سهمیه باقیمانده توکن سازمان\n"
            "- `/rbac audit [tenant_id]` : مشاهده لاگ ممیزی و رویدادهای امنیتی\n"
            "- `/rbac reset` : بازنشانی تنظیمات به مقادیر اولیه"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_rbac_engine()

    if subcmd == "tenant":
        if len(parts) < 2:
            return "❌ دستور نامعتبر. مثال: `/rbac tenant list` یا `/rbac tenant create`"
        action = parts[1].lower()
        if action == "list":
            tenants = engine.list_tenants()
            lines = ["📋 **فهرست سازمان‌های ثبت‌شده:**"]
            for t in tenants:
                q = t["quota"]
                b_str = f"{q['monthly_token_budget']:,}"
                lines.append(
                    f"- **{t['name']}** (`{t['tenant_id']}`) | پلن: `{t['tier']}` | سهمیه: {b_str}"
                )
            return "\n".join(lines)
        elif action == "create":
            if len(parts) < 4:
                return "❌ مشخصات ناقص است: `/rbac tenant create <id> <name> [budget]`"
            tid, name = parts[2], parts[3]
            budget = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1_000_000
            t = engine.create_tenant(
                tenant_id=tid,
                name=name,
                tier=TenantTier.PRO,
                monthly_token_budget=budget,
            )
            return f"✅ سازمان **{t.name}** (`{t.tenant_id}`) با سهمیه `{budget:,}` ایجاد شد."

    elif subcmd == "user":
        if len(parts) < 2:
            return "❌ دستور نامعتبر. مثال: `/rbac user list` یا `/rbac user create`"
        action = parts[1].lower()
        if action == "list":
            tid = parts[2] if len(parts) > 2 else None
            users = engine.list_users(tid)
            lines = [f"👥 **فهرست کاربران{' سازمان ' + tid if tid else ''}:**"]
            for u in users:
                lines.append(
                    f"- **{u['username']}** (`{u['user_id']}`) | سازمان: `{u['tenant_id']}`"
                )
            return "\n".join(lines)
        elif action == "create":
            if len(parts) < 5:
                return "❌ مشخصات ناقص است: `/rbac user create <user_id> <tenant_id> <name> [role]`"
            uid, tid, uname = parts[2], parts[3], parts[4]
            role_str = parts[5].lower() if len(parts) > 5 else "developer"
            try:
                role = Role(role_str)
            except ValueError:
                role = Role.DEVELOPER
            try:
                user = engine.create_user(uid, tid, uname, roles=[role])
                return f"✅ کاربر **{user.username}** با نقش `{role.value}` ثبت شد."
            except Exception as e:
                return f"❌ خطا: {e}"

    elif subcmd == "check":
        if len(parts) < 4:
            return "❌ فرمت نامعتبر: `/rbac check <tenant_id> <user_id> <permission>`"
        tid, uid, perm = parts[1], parts[2], parts[3]
        ok, reason = engine.verify_access(tid, uid, perm)
        status_icon = "✅ مجاز" if ok else "❌ غیرمجاز"
        return f"🛡️ **نتیجه ارزیابی دسترسی:** {status_icon}\n- علت: {reason}"

    elif subcmd == "quota":
        tid = parts[1] if len(parts) > 1 else "tenant-root"
        tenant = engine.get_tenant(tid)
        if not tenant:
            return f"❌ سازمان `{tid}` یافت نشد."
        q = tenant.quota
        u = tenant.usage
        rem_m = max(0, q.monthly_token_budget - u.monthly_tokens_used)
        return (
            f"📊 **وضعیت سهمیه سازمان {tenant.name} (`{tid}`):**\n"
            f"- مصرف ماهانه: `{u.monthly_tokens_used:,}` از `{q.monthly_token_budget:,}` توکن\n"
            f"- باقیمانده ماهانه: `{rem_m:,}` توکن\n"
            f"- مصرف روزانه: `{u.daily_tokens_used:,}` از `{q.daily_token_budget:,}` توکن\n"
            f"- کل درخواست‌ها: `{u.total_requests}` | تعداد فراخوانی ابزار: `{u.tool_calls_count}`"
        )

    elif subcmd == "audit":
        tid = parts[1] if len(parts) > 1 else None
        return engine.export_audit_markdown(tid)

    elif subcmd == "reset":
        engine.reset()
        return "🔄 **موتور دسترسی سازمانی (RBAC) با موفقیت ریست شد.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/rbac` را بزنید."
