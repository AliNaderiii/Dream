"""Datetime tool for Jalali date and local time lookup."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dream.tools.base import tool


@tool(risk="safe")
def get_datetime(timezone_name: str = "Asia/Tehran") -> str:
    """Return the current Jalali date and local time for an IANA time zone.

    :param timezone_name: IANA zone name, such as ``Asia/Tehran``.
    """
    from datetime import timezone as dt_timezone

    import dream.tools as _dt
    from dream.jalali import gregorian_to_jalali

    zone_info_cls = getattr(_dt, "ZoneInfo", ZoneInfo)
    datetime_cls = getattr(_dt, "datetime", datetime)

    try:
        zoneinfo = zone_info_cls(timezone_name)
        zone = "\u062a\u0647\u0631\u0627\u0646" if timezone_name == "Asia/Tehran" else timezone_name
    except ZoneInfoNotFoundError:
        # Embeddable Windows CPython ships without the IANA database.
        zoneinfo = datetime_cls.now().astimezone().tzinfo or dt_timezone.utc
        zone = timezone_name
    moment = datetime_cls.now(zoneinfo)
    jy, jm, jd = gregorian_to_jalali(moment.year, moment.month, moment.day)
    digits = str.maketrans(
        "0123456789",
        "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    )
    date = f"{jy:04d}/{jm:02d}/{jd:02d}".translate(digits)
    clock = f"{moment.hour:02d}:{moment.minute:02d}".translate(digits)
    return (
        "\u0627\u0645\u0631\u0648\u0632 "
        f"{date}"
        "\u060c \u0633\u0627\u0639\u062a "
        f"{clock}"
        " \u0628\u0647 \u0648\u0642\u062a "
        f"{zone}"
        " \u0627\u0633\u062a."
    )
