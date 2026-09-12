"""Master Dashboard Engine for Dream Agent Operations and Control Tower."""

from __future__ import annotations

import json
from typing import Any

from dream.dashboard.aggregator import DashboardAggregator
from dream.dashboard.renderer import DashboardRenderer
from dream.dashboard.types import ControlTowerSnapshot, DashboardConfig, DashboardTheme


class DashboardEngine:
    """Master controller managing real-time telemetry, visual rendering, and health reports."""

    def __init__(self) -> None:
        self.aggregator = DashboardAggregator()
        self.renderer = DashboardRenderer()

    def get_snapshot(self) -> ControlTowerSnapshot:
        """Capture and return latest real-time control tower snapshot."""
        return self.aggregator.collect_snapshot()

    def get_overview(self) -> dict[str, Any]:
        """Return executive status overview of all subsystems and overall health."""
        snap = self.get_snapshot()
        return {
            "snapshot_id": snap.snapshot_id,
            "overall_health": snap.overall_health.value,
            "total_subsystems": snap.total_subsystems,
            "healthy_subsystems": snap.healthy_subsystems,
            "active_alerts_count": len(snap.active_alerts),
            "token_economics": snap.token_economics,
            "subsystems_overview": {
                name: {"status": s.status.value, "active_count": s.active_items_count}
                for name, s in snap.subsystems.items()
            },
        }

    def get_subsystem_telemetry(self, subsystem_name: str) -> dict[str, Any]:
        """Retrieve detailed metrics for a specific subsystem."""
        snap = self.get_snapshot()
        sub = snap.subsystems.get(subsystem_name.lower())
        if not sub:
            return {"success": False, "error": f"زیرسیستم `{subsystem_name}` یافت نشد."}
        return {"success": True, "subsystem": sub.to_dict()}

    def render_html(
        self,
        theme: str = "dark",
        locale: str = "fa",
    ) -> str:
        """Render complete standalone HTML/SVG control tower dashboard."""
        snap = self.get_snapshot()
        try:
            th_enum = DashboardTheme(theme.lower())
        except ValueError:
            th_enum = DashboardTheme.DARK

        cfg = DashboardConfig(theme=th_enum, locale=locale)
        return self.renderer.render_html(snap, cfg)

    def export_metrics_markdown(self) -> str:
        """Format integrated system metrics into structured Markdown table."""
        snap = self.get_snapshot()
        saved_tok = snap.token_economics.get("tokens_saved_by_cache", 0)
        lines = [
            "# 🎛️ گزارش وضعیت برج مراقبت دریم (Control Tower Metrics)",
            f"- **وضعیت کلی سامانه**: `● {snap.overall_health.value.upper()}`",
            f"- **زیرسیستم‌ها**: `{snap.healthy_subsystems}/{snap.total_subsystems}` فعال",
            f"- **توکن‌های ذخیره‌شده**: `{saved_tok:,}`",
            "",
            "## 📊 ماتریس سلامت و متریک‌های زیرسیستم‌ها:",
            "",
            "| زیرسیستم | نام فارسی | وضعیت | آیتم‌های فعال | آپ‌تایم | شاخص کلیدی |",
            "| :--- | :--- | :---: | :---: | :---: | :--- |",
        ]

        for name, s in snap.subsystems.items():
            st_icon = "🟢" if s.status.value == "healthy" else "🟡"
            fm = next(iter(s.metrics.items())) if s.metrics else ("-", "-")
            lines.append(
                f"| `{name}` | {s.display_name_fa} | {st_icon} `{s.status.value}` | "
                f"`{s.active_items_count}` | `{int(s.uptime_sec)}s` | {fm[0]}: `{fm[1]}` |"
            )

        if snap.active_alerts:
            lines.extend([
                "",
                "## ⚠️ هشدارهای فعال سیستم:",
                "",
            ])
            for alt in snap.active_alerts:
                lines.append(f"- **[{alt.severity.upper()}]** ({alt.subsystem}): {alt.message_fa}")

        return "\n".join(lines)

    def export_json(self) -> str:
        """Export raw snapshot data in JSON format."""
        snap = self.get_snapshot()
        return json.dumps(snap.to_dict(), indent=2, ensure_ascii=False)

    def reset(self) -> None:
        """Reset aggregator telemetry timers."""
        self.aggregator = DashboardAggregator()


# Global Singleton
_GLOBAL_DASHBOARD_ENGINE: DashboardEngine | None = None


def get_dashboard_engine() -> DashboardEngine:
    """Retrieve global singleton instance of DashboardEngine."""
    global _GLOBAL_DASHBOARD_ENGINE
    if _GLOBAL_DASHBOARD_ENGINE is None:
        _GLOBAL_DASHBOARD_ENGINE = DashboardEngine()
    return _GLOBAL_DASHBOARD_ENGINE
