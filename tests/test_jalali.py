"""Pin the Jalali-Gregorian conversion used at the reminder edges.

The owner supplies dates in Jalali; storage keeps Unix timestamps.
Conversion happens only when reading a Jalali date and when printing one
back. The nine hand-checked pairs were verified by hand against an
external converter, and the exhaustive round-trip from 1990 to 2030
must be perfect — fifteen thousand dates, zero mismatches. If the
round-trip gives any mismatch, the forty-line algorithm is wrong.
Leap handling is pinned too: Esfand has 30 days only in a leap year.
"""

from __future__ import annotations

import datetime

import pytest

from dream.jalali import gregorian_to_jalali, is_jalali_leap, jalali_to_gregorian

# Nine hand-checked pairs, Gregorian is Jalali
_PAIRS = [
    ((2026, 8, 7), (1405, 5, 16)),
    ((2026, 3, 21), (1405, 1, 1)),
    ((2025, 3, 21), (1404, 1, 1)),
    ((2024, 3, 20), (1403, 1, 1)),
    ((2026, 10, 7), (1405, 7, 15)),
    ((2025, 2, 28), (1403, 12, 10)),
    ((2024, 2, 29), (1402, 12, 10)),
    ((2022, 3, 20), (1400, 12, 29)),
    ((2022, 3, 21), (1401, 1, 1)),
]


@pytest.mark.parametrize("gregorian,jalali", _PAIRS)
def test_gregorian_to_jalali_hand_checked(gregorian, jalali):
    assert gregorian_to_jalali(*gregorian) == jalali


@pytest.mark.parametrize("gregorian,jalali", _PAIRS)
def test_jalali_to_gregorian_hand_checked(gregorian, jalali):
    assert jalali_to_gregorian(*jalali) == gregorian


def test_exhaustive_round_trip_1990_to_2030():
    mismatches = 0
    checked = 0
    day = datetime.date(1990, 1, 1)
    end = datetime.date(2030, 12, 31)
    one = datetime.timedelta(days=1)
    while day <= end:
        jy, jm, jd = gregorian_to_jalali(day.year, day.month, day.day)
        gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
        if (gy, gm, gd) != (day.year, day.month, day.day):
            mismatches += 1
        checked += 1
        day += one
    assert checked == 14975
    assert mismatches == 0


def test_leap_year_accepts_esfand_30():
    # 1399 is leap per 33-year cycle, 1400 is common
    assert is_jalali_leap(1399) is True
    assert is_jalali_leap(1400) is False
    # leap accepts 30
    gy, gm, gd = jalali_to_gregorian(1399, 12, 30)
    assert gregorian_to_jalali(gy, gm, gd) == (1399, 12, 30)
    # common rejects 30
    with pytest.raises(ValueError):
        jalali_to_gregorian(1400, 12, 30)


def test_invalid_jalali_dates_rejected():
    with pytest.raises(ValueError):
        jalali_to_gregorian(1405, 13, 1)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1405, 0, 10)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1405, 7, 31)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1400, 12, 30)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1405, 1, 0)
    with pytest.raises(ValueError):
        jalali_to_gregorian(1405, 1, 32)


def test_invalid_gregorian_dates_rejected():
    with pytest.raises(ValueError):
        gregorian_to_jalali(2026, 13, 1)
    with pytest.raises(ValueError):
        gregorian_to_jalali(2026, 2, 30)
    with pytest.raises(ValueError):
        gregorian_to_jalali(2023, 2, 29)
    with pytest.raises(ValueError):
        gregorian_to_jalali(2026, 4, 31)
    # valid leap day
    assert gregorian_to_jalali(2024, 2, 29) == (1402, 12, 10)
