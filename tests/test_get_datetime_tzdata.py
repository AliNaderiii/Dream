"""get_datetime must not crash when the IANA database is missing."""

from __future__ import annotations

from zoneinfo import ZoneInfoNotFoundError

from dream.tools import get_datetime


def test_get_datetime_survives_missing_tzdata(monkeypatch):
    def boom(_name: str):
        raise ZoneInfoNotFoundError("Asia/Tehran")

    monkeypatch.setattr("dream.tools.ZoneInfo", boom)
    text = get_datetime("Asia/Tehran")
    assert "\u0627\u0633\u062a" in text
    assert "\u0627\u0645\u0631\u0648\u0632" in text


def test_get_datetime_tehran_when_tzdata_present():
    text = get_datetime("Asia/Tehran")
    assert "\u062a\u0647\u0631\u0627\u0646" in text
    assert "\u0627\u0645\u0631\u0648\u0632" in text
