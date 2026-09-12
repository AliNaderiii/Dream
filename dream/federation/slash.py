"""Slash command dispatcher for Multi-Agent Neural Mesh & Distributed Federation."""

from __future__ import annotations

import shlex

from dream.federation.engine import get_federation_engine


def handle_federation_command(args_str: str) -> str:
    """Handle /federation slash commands.

    Usage:
        /federation topology
        /federation peers
        /federation register <id> <name_fa> <endpoint> [caps]
        /federation delegate <task_name> <capability>
        /federation elect [candidate_id]
        /federation metrics
        /federation reset
    """
    if not args_str.strip():
        return (
            "🌐 **راهنمای دستورات شبکه فدراسیون عامل‌ها (Neural Mesh Federation):**\n\n"
            "- `/federation topology` : مشاهده نقشه توپولوژی و وضعیت لیدر کلاستر\n"
            "- `/federation peers` : لیست تمام گره‌های همتای فعال\n"
            "- `/federation register <id> <name> <ep> [caps]` : اتصال گره جدید به شبکه\n"
            "- `/federation delegate <task> <cap>` : واگذاری هوشمند وظیفه به گره متخصص\n"
            "- `/federation elect [id]` : برگزاری انتخابات لیدر توزیع‌شده (Raft-lite)\n"
            "- `/federation metrics` : تله‌متری و شاخص‌های سلامت شبکه مش\n"
            "- `/federation reset` : بازنشانی کلاستر فدراسیون"
        )

    try:
        parts = shlex.split(args_str)
    except ValueError:
        parts = args_str.split()

    subcmd = parts[0].lower()
    engine = get_federation_engine()

    if subcmd in ("topology", "status"):
        topo = engine.get_topology()
        lines = [
            f"🌐 **توپولوژی کلاستر فدراسیون (`{topo.cluster_id}`):**",
            f"- لیدر فعلی: `{topo.leader_id or 'نامشخص'}` | دوره (Term): `{topo.current_term}`",
            f"- تعداد گره‌ها: `{topo.healthy_peers}/{topo.total_peers}` سالم",
            f"- وظایف فعال توزیع‌شده: `{topo.active_tasks_count}`",
            "",
            "**گره‌های متصل در شبکه:**",
        ]
        for p in topo.peers.values():
            st_icon = "🟢" if p.health.value == "healthy" else "🟡"
            role_badge = "👑 [LEADER]" if p.role.value == "leader" else "[FOLLOWER]"
            caps_str = ", ".join(p.capabilities[:3])
            lines.append(
                f"- {st_icon} `{p.node_id}` ({p.display_name_fa}) {role_badge} | "
                f"تخصص: `{caps_str}`"
            )
        return "\n".join(lines)

    elif subcmd == "peers":
        topo = engine.get_topology()
        lines = [f"👥 **لیست گره‌های همتا ({len(topo.peers)} گره):**"]
        for p in topo.peers.values():
            lines.append(
                f"- **{p.display_name_fa}** (`{p.node_id}`): `{p.endpoint}` "
                f"| لود: `{int(p.workload_score * 100)}%`"
            )
        return "\n".join(lines)

    elif subcmd == "register":
        if len(parts) < 4:
            return "❌ ساختار دستور: `/federation register <id> <name_fa> <endpoint> [cap1,cap2]`"
        nid, name_fa, ep = parts[1], parts[2], parts[3]
        caps = parts[4].split(",") if len(parts) > 4 else ["general"]
        node = engine.register_peer(nid, name_fa, ep, capabilities=caps)
        return f"✅ **گره `{node.display_name_fa}` (`{node.node_id}`) با موفقیت به شبکه متصل شد.**"

    elif subcmd == "delegate":
        if len(parts) < 3:
            return "❌ ساختار دستور: `/federation delegate <task_name> <required_capability>`"
        tname, cap = parts[1], parts[2]
        res = engine.delegate_task(tname, cap, {})
        return (
            f"🚀 **وظیفه `{tname}` با شناسه `{res['task_id']}` واگذار شد.**\n"
            f"- گره مجری: `{res['assigned_node_id']}` | وضعیت: `{res['status']}`"
        )

    elif subcmd in ("elect", "election"):
        cand = parts[1] if len(parts) > 1 else ""
        el = engine.trigger_leader_election(cand or None)
        return f"🗳️ **نتیجه انتخابات دوره {el['term']}:** {el['summary_fa']}"

    elif subcmd == "metrics":
        m = engine.get_metrics()
        return (
            f"📊 **تله‌متری فدراسیون دریم:**\n"
            f"- کلاستر: `{m['cluster_id']}` | لیدر: `{m['leader_id']}`\n"
            f"- گره‌های سالم: `{m['healthy_peers']}/{m['total_peers']}`\n"
            f"- وظایف پردازش‌شده: `{m['total_delegated_tasks']}`"
        )

    elif subcmd == "reset":
        engine.reset()
        return "🔄 **کلاستر فدراسیون عامل‌ها بازنشانی شد.**"

    return f"❌ دستور ناآشنا: `{subcmd}`. برای راهنما `/federation` را وارد کنید."
