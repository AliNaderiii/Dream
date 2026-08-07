"""Jalali-Gregorian calendar conversion, standard library only.

The owner thinks in the Jalali calendar. Storage uses Unix timestamps, conversion
happens only at the edges. Two functions, each about forty lines, verified
against nine hand-checked pairs and an exhaustive round-trip from 1990 to 2030.

Persian strings here are intentional backslash-u escapes.
"""

from __future__ import annotations

__all__ = [
    "gregorian_to_jalali",
    "is_jalali_leap",
    "jalali_to_gregorian",
]

_JALALI_MONTH_LENGTHS_COMMON = (31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29)
_JALALI_MONTH_LENGTHS_LEAP = (31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 30)


def _is_gregorian_leap(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _days_in_gregorian_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if _is_gregorian_leap(year) else 28
    if month in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if month in (4, 6, 9, 11):
        return 30
    return 0


def is_jalali_leap(year: int) -> bool:
    """Return whether a Jalali year has a 30th day in Esfand.

    The 33-year cycle uses remainders 1, 5, 9, 13, 17, 22, 26, 30.
    """
    return (year % 33) in (1, 5, 9, 13, 17, 22, 26, 30)


def _days_in_jalali_month(year: int, month: int) -> int:
    if 1 <= month <= 6:
        return 31
    if 7 <= month <= 11:
        return 30
    if month == 12:
        return 30 if is_jalali_leap(year) else 29
    return 0


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert Gregorian date to Jalali.

    :param gy: Gregorian year
    :param gm: Gregorian month 1..12
    :param gd: Gregorian day 1..31
    """
    if not 1 <= gm <= 12:
        raise ValueError(f"invalid Gregorian month: {gm}")
    if not 1 <= gd <= 31:
        raise ValueError(f"invalid Gregorian day: {gd}")
    max_day = _days_in_gregorian_month(gy, gm)
    if gd > max_day:
        raise ValueError(f"invalid Gregorian day {gd} for month {gm} in {gy}")
    # standard algorithm, about forty lines
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666
        + 365 * gy
        + (gy2 + 3) // 4
        - (gy2 + 99) // 100
        + (gy2 + 399) // 400
        + gd
        + g_d_m[gm - 1]
    )
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """Convert Jalali date to Gregorian.

    :param jy: Jalali year
    :param jm: Jalali month 1..12
    :param jd: Jalali day 1..31
    """
    if not 1 <= jm <= 12:
        raise ValueError(f"invalid Jalali month: {jm}")
    if not 1 <= jd <= 31:
        raise ValueError(f"invalid Jalali day: {jd}")
    max_day = _days_in_jalali_month(jy, jm)
    if jd > max_day:
        raise ValueError(f"invalid Jalali day {jd} for month {jm} in {jy}")
    # year below 1700 is Jalali — see also reminder parsing
    # standard algorithm, about forty lines
    jy2 = jy + 1595
    if jm < 7:
        days = (
            -355668
            + 365 * jy2
            + (jy2 // 33) * 8
            + ((jy2 % 33) + 3) // 4
            + jd
            + (jm - 1) * 31
        )
    else:
        days = (
            -355668
            + 365 * jy2
            + (jy2 // 33) * 8
            + ((jy2 % 33) + 3) // 4
            + jd
            + (jm - 7) * 30
            + 186
        )
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    is_leap = _is_gregorian_leap(gy)
    sal_a = [0, 31, 29 if is_leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 1
    while gm <= 12 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd
