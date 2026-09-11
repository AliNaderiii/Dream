"""Built-in Jalali & Solar Hijri Calendar Calculator Plugin."""

from __future__ import annotations

import json
from typing import Any

from dream.plugins.base import BasePlugin
from dream.plugins.types import PluginManifest


class CalendarCalcPlugin(BasePlugin):
    """Provides Solar Hijri (Jalali) date arithmetic and Iranian holiday calculations."""

    def __init__(self) -> None:
        manifest = PluginManifest(
            name="calendar_calc_plugin",
            version="1.0.0",
            author="Dream Core Team",
            description_en="Jalali date calculations, business day counting, and Persian tools.",
            description_fa="محاسبات پیشرفته تاریخ جلالی، شمارش روزهای کاری و تبدیل تاریخ شمسی.",
            permissions=["tools"],
        )
        super().__init__(manifest)

    def register_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "calculate_jalali_date",
                "description": (
                    "Add or subtract days from a Jalali date (e.g. '1403/06/15' + 45 days).\n"
                    "محاسبه و افزودن یا کسر روز از یک تاریخ شمسی (مثلاً ۱۴۰۳/۰۶/۱۵ + ۴۵ روز)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date_str": {
                            "type": "string",
                            "description": "Jalali date in YYYY/MM/DD (e.g. '1403/06/20')",
                        },
                        "days_to_add": {
                            "type": "integer",
                            "description": "Days to add (positive) or subtract (negative)",
                        },
                    },
                    "required": ["date_str", "days_to_add"],
                },
                "handler": self.calculate_jalali_date,
            }
        ]

    def calculate_jalali_date(self, date_str: str, days_to_add: int) -> str:
        """Perform simple Solar Hijri day arithmetic."""
        clean = date_str.replace("-", "/").strip()
        parts = clean.split("/")
        if len(parts) != 3:
            return json.dumps(
                {"error": "فرمت تاریخ نامعتبر است. لطفاً به صورت YYYY/MM/DD وارد کنید."}
            )

        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return json.dumps({"error": "ارقام تاریخ نامعتبر هستند."})

        # Calculate approximate days in Jalali months
        # Months 1-6 have 31 days, 7-11 have 30 days, month 12 has 29 (or 30 in leap year)
        def days_in_month(y: int, m: int) -> int:
            if 1 <= m <= 6:
                return 31
            if 7 <= m <= 11:
                return 30
            # Check leap year (approximate Jalali leap cycle)
            is_leap = ((((y - (474 if y > 0 else 473)) % 2820) + 474 + 38) * 682) % 2816 < 682
            return 30 if is_leap else 29

        curr_y, curr_m, curr_d = year, month, day

        remaining_days = days_to_add
        if remaining_days >= 0:
            while remaining_days > 0:
                month_len = days_in_month(curr_y, curr_m)
                days_left_in_month = month_len - curr_d
                if remaining_days <= days_left_in_month:
                    curr_d += remaining_days
                    remaining_days = 0
                else:
                    remaining_days -= (days_left_in_month + 1)
                    curr_d = 1
                    curr_m += 1
                    if curr_m > 12:
                        curr_m = 1
                        curr_y += 1
        else:
            remaining_days = abs(remaining_days)
            while remaining_days > 0:
                if remaining_days < curr_d:
                    curr_d -= remaining_days
                    remaining_days = 0
                else:
                    remaining_days -= curr_d
                    curr_m -= 1
                    if curr_m < 1:
                        curr_m = 12
                        curr_y -= 1
                    curr_d = days_in_month(curr_y, curr_m)

        result_date = f"{curr_y:04d}/{curr_m:02d}/{curr_d:02d}"
        res = {
            "initial_date": date_str,
            "days_offset": days_to_add,
            "result_date": result_date,
            "summary_fa": f"تاریخ حاصل: {result_date} (پس از {days_to_add} روز).",
        }
        return json.dumps(res, ensure_ascii=False, indent=2)
