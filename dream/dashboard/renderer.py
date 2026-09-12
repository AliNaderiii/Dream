"""HTML, SVG, and Visual Artifact Renderer for the Agent Control Tower."""

from __future__ import annotations

from dream.dashboard.types import (
    ControlTowerSnapshot,
    DashboardConfig,
    SystemHealthStatus,
)


class DashboardRenderer:
    """Renders self-contained responsive HTML and SVG dashboards for Dream."""

    @staticmethod
    def render_html(snapshot: ControlTowerSnapshot, config: DashboardConfig | None = None) -> str:
        """Generate a complete, modern, self-contained HTML/CSS/SVG dashboard."""
        cfg = config or DashboardConfig()
        is_rtl = cfg.locale == "fa"
        dir_attr = "rtl" if is_rtl else "ltr"
        lang_attr = "fa" if is_rtl else "en"

        health_color = "#10b981"
        if snapshot.overall_health == SystemHealthStatus.DEGRADED:
            health_color = "#f59e0b"
        elif snapshot.overall_health == SystemHealthStatus.CRITICAL:
            health_color = "#ef4444"

        subsystems_cards_html = []
        for _name, sub in snapshot.subsystems.items():
            st_color = "#10b981" if sub.status == SystemHealthStatus.HEALTHY else "#f59e0b"
            metrics_items = "".join(
                f"<div class='metric-item'><span class='metric-key'>{k}:</span> "
                f"<span class='metric-val'>{v}</span></div>"
                for k, v in list(sub.metrics.items())[:3]
            )

            title_str = sub.display_name_fa if is_rtl else sub.name.upper()
            act_label = "آیتم‌های فعال" if is_rtl else "Active"
            upt_label = "آپ‌تایم" if is_rtl else "Uptime"

            card_html = f"""
            <div class="card">
                <div class="card-header">
                    <h3>{title_str}</h3>
                    <span class="badge" style="background-color: {st_color}22; color: {st_color};">
                        ● {sub.status.value.upper()}
                    </span>
                </div>
                <div class="card-body">
                    <div class="metric-grid">
                        <div class="metric-box">
                            <span class="m-title">{act_label}</span>
                            <span class="m-val">{sub.active_items_count}</span>
                        </div>
                        <div class="metric-box">
                            <span class="m-title">{upt_label}</span>
                            <span class="m-val">{int(sub.uptime_sec)}s</span>
                        </div>
                    </div>
                    <div class="metrics-detail">
                        {metrics_items}
                    </div>
                </div>
            </div>
            """
            subsystems_cards_html.append(card_html)

        cards_combined = "\n".join(subsystems_cards_html)

        # SVG Topo Graph
        svg_topo = """
        <svg class="topo-svg" viewBox="0 0 800 240" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="glow" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.8"/>
                    <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0.8"/>
                </linearGradient>
            </defs>
            <line x1="400" y1="120" x2="150" y2="60" stroke="#374151" stroke-width="2"/>
            <line x1="400" y1="120" x2="650" y2="60" stroke="#374151" stroke-width="2"/>
            <line x1="400" y1="120" x2="150" y2="180" stroke="#374151" stroke-width="2"/>
            <line x1="400" y1="120" x2="650" y2="180" stroke="#374151" stroke-width="2"/>
            <line x1="400" y1="120" x2="400" y2="30" stroke="#374151" stroke-width="2"/>
            <line x1="400" y1="120" x2="400" y2="210" stroke="#374151" stroke-width="2"/>

            <circle cx="400" cy="120" r="35" fill="url(#glow)"/>
            <text x="400" y="125" font-size="12" fill="#fff" text-anchor="middle">Dream Core</text>

            <circle cx="150" cy="60" r="24" fill="#1f2937" stroke="#3b82f6" stroke-width="2"/>
            <text x="150" y="64" font-size="10" fill="#93c5fd" text-anchor="middle">Swarm</text>

            <circle cx="650" cy="60" r="24" fill="#1f2937" stroke="#8b5cf6" stroke-width="2"/>
            <text x="650" y="64" font-size="10" fill="#c4b5fd" text-anchor="middle">Knowledge</text>

            <circle cx="150" cy="180" r="24" fill="#1f2937" stroke="#10b981" stroke-width="2"/>
            <text x="150" y="184" font-size="10" fill="#6ee7b7" text-anchor="middle">Cache</text>

            <circle cx="650" cy="180" r="24" fill="#1f2937" stroke="#ec4899" stroke-width="2"/>
            <text x="650" y="184" font-size="10" fill="#f472b6" text-anchor="middle">Duplex</text>

            <circle cx="400" cy="30" r="20" fill="#1f2937" stroke="#f59e0b" stroke-width="2"/>
            <text x="400" y="34" font-size="9" fill="#fcd34d" text-anchor="middle">RBAC</text>

            <circle cx="400" cy="210" r="20" fill="#1f2937" stroke="#06b6d4" stroke-width="2"/>
            <text x="400" y="214" font-size="9" fill="#67e8f9" text-anchor="middle">Reactive</text>
        </svg>
        """

        tag_subtitle = (
            "سامانه مانیتورینگ بلادرنگ عامل دریم"
            if is_rtl
            else "Real-time control tower for Dream Agent"
        )
        tag_status = (
            f"وضعیت سیستم: {snapshot.overall_health.value.upper()}"
            if is_rtl
            else f"System Status: {snapshot.overall_health.value.upper()}"
        )
        topo_header = (
            "🗺️ نقشه توپولوژی ارتباطی زیرسیستم‌های هوشمند Dream"
            if is_rtl
            else "🗺️ Dream Subsystems Topology & Neural Swarm Map"
        )

        html_content = f"""<!DOCTYPE html>
<html lang="{lang_attr}" dir="{dir_attr}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{cfg.app_title}</title>
    <style>
        :root {{
            --bg-color: #0b0f19;
            --card-bg: #111827;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
            --border-color: #1f2937;
            --accent: #6366f1;
        }}
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }}
        body {{
            background-color: var(--bg-color);
            color: var(--text-main);
            padding: 24px;
            line-height: 1.5;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-size: 24px;
            font-weight: 800;
            background: linear-gradient(135deg, #60a5fa, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: {health_color};
        }}
        .topo-container {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 24px;
            text-align: center;
        }}
        .topo-svg {{
            width: 100%;
            max-height: 220px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .card-header h3 {{
            font-size: 15px;
            font-weight: 700;
        }}
        .badge {{
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 8px;
        }}
        .metric-box {{
            background: #1f2937;
            padding: 8px;
            border-radius: 6px;
            text-align: center;
        }}
        .metric-box .m-title {{
            display: block;
            font-size: 11px;
            color: var(--text-muted);
        }}
        .metric-box .m-val {{
            font-size: 16px;
            font-weight: 700;
            color: #60a5fa;
        }}
        .metrics-detail {{
            font-size: 12px;
            color: var(--text-muted);
            border-top: 1px solid var(--border-color);
            padding-top: 8px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}
        .metric-item {{
            display: flex;
            justify-content: space-between;
        }}
        .metric-val {{
            font-weight: 600;
            color: var(--text-main);
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>{cfg.app_title}</h1>
            <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">
                {tag_subtitle}
            </p>
        </div>
        <div class="status-pill">
            <span style="font-size: 18px;">●</span>
            <span>{tag_status}</span>
        </div>
    </div>

    <div class="topo-container">
        <h4 style="font-size: 13px; color: var(--text-muted); margin-bottom: 8px;">
            {topo_header}
        </h4>
        {svg_topo}
    </div>

    <div class="grid">
        {cards_combined}
    </div>
</body>
</html>"""
        return html_content
