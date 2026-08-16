"""Turn everyday English or Persian phrasing into a cron expression.

Gate G7 requires this be pure pattern matching — no model call — so a schedule
parses identically offline, in CI, and in the packaged app.

The design is compositional rather than a lookup table of whole phrases. Input
is normalised once (``normalize_fa`` folds Persian and Arabic digits to ASCII,
unifies the Arabic/Persian yeh and kaf forms, and turns ZWNJ into a space),
then four independent readers pull out the interval, the time of day, the day
scope, and the month scope. The two
languages therefore share every downstream rule, and adding a synonym is a
one-line change to a vocabulary tuple instead of a new pattern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dream.memory import normalize_fa

__all__ = ["NL_EXAMPLES", "ScheduleParseError", "nl_to_cron"]


class ScheduleParseError(ValueError):
    """Raised when no pattern matches — the caller must not guess."""


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

# Cron numbers Sunday as 0. The Persian week begins on Saturday, so the Persian
# names are mapped by their own order, not by translating the English list.
_WEEKDAYS: dict[str, int] = {
    "sunday": 0, "sun": 0,
    "monday": 1, "mon": 1,
    "tuesday": 2, "tue": 2, "tues": 2,
    "wednesday": 3, "wed": 3,
    "thursday": 4, "thu": 4, "thur": 4, "thurs": 4,
    "friday": 5, "fri": 5,
    "saturday": 6, "sat": 6,
    # Gloss: یکشنبه Sunday, دوشنبه Monday, سه شنبه Tuesday, چهارشنبه Wednesday,
    # پنجشنبه Thursday, جمعه Friday, شنبه Saturday.
    "\u06cc\u06a9\u0634\u0646\u0628\u0647": 0,
    "\u062f\u0648\u0634\u0646\u0628\u0647": 1,
    "\u0633\u0647 \u0634\u0646\u0628\u0647": 2,
    "\u0633\u0647\u0634\u0646\u0628\u0647": 2,
    "\u0686\u0647\u0627\u0631\u0634\u0646\u0628\u0647": 3,
    "\u067e\u0646\u062c\u0634\u0646\u0628\u0647": 4,
    "\u067e\u0646\u062c \u0634\u0646\u0628\u0647": 4,
    "\u062c\u0645\u0639\u0647": 5,
    "\u0634\u0646\u0628\u0647": 6,
}

# Longest first: "سه شنبه" must be tried before the "شنبه" it contains.
_WEEKDAY_ORDER = sorted(_WEEKDAYS, key=len, reverse=True)

_MONTH_WORDS = ("month", "monthly", "\u0645\u0627\u0647")  # Gloss: ماه month
_WEEK_WORDS = ("week", "weekly", "\u0647\u0641\u062a\u0647")  # Gloss: هفته week
_DAY_WORDS = ("day", "daily", "\u0631\u0648\u0632")  # Gloss: روز day
_HOUR_WORDS = ("hour", "hourly", "\u0633\u0627\u0639\u062a")  # Gloss: ساعت hour
_MINUTE_WORDS = ("minute", "min", "\u062f\u0642\u06cc\u0642\u0647")  # Gloss: دقیقه minute
_YEAR_WORDS = ("year", "yearly", "annually", "\u0633\u0627\u0644")  # Gloss: سال year

# Gloss: هر/هرروز every, روزهای کاری weekdays, آخر هفته weekend.
_EVERY = ("every", "each", "\u0647\u0631")
_WEEKDAY_SCOPE = (
    "weekday",
    "weekdays",
    "week day",
    "week days",
    "business day",
    "business days",
    "working day",
    "working days",
    "\u0631\u0648\u0632\u0647\u0627\u06cc \u06a9\u0627\u0631\u06cc",
    "\u0631\u0648\u0632 \u06a9\u0627\u0631\u06cc",
)
_WEEKEND_SCOPE = (
    "weekend",
    "weekends",
    "\u0622\u062e\u0631 \u0647\u0641\u062a\u0647",
    "\u0627\u062e\u0631 \u0647\u0641\u062a\u0647",
    "\u067e\u0627\u06cc\u0627\u0646 \u0647\u0641\u062a\u0647",
)

#: The Iranian working week runs Saturday to Wednesday; Thursday and Friday are
#: the weekend. A Persian "روزهای کاری" therefore cannot mean the ISO ``1-5``.
_IRANIAN_WORKDAYS = "6,0,1,2,3"
_IRANIAN_WEEKEND = "4,5"

# Gloss: صبح morning, ظهر noon, بعدازظهر/عصر afternoon, شب night, نیمه شب midnight.
_MORNING = ("am", "a.m", "morning", "\u0635\u0628\u062d")
_AFTERNOON = (
    "pm",
    "p.m",
    "afternoon",
    "evening",
    "night",
    "\u0628\u0639\u062f\u0627\u0632\u0638\u0647\u0631",
    "\u0628\u0639\u062f \u0627\u0632 \u0638\u0647\u0631",
    "\u0639\u0635\u0631",
    "\u0634\u0628",
)
_NOON = ("noon", "midday", "\u0638\u0647\u0631")
_MIDNIGHT = (
    "midnight",
    "\u0646\u06cc\u0645\u0647 \u0634\u0628",
    "\u0646\u06cc\u0645\u0647\u200c\u0634\u0628",
)

_NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "half an": 30,
    # Gloss: یک 1, دو 2, سه 3, چهار 4, پنج 5, شش 6, ده 10, پانزده 15, نیم half.
    "\u06cc\u06a9": 1, "\u062f\u0648": 2, "\u0633\u0647": 3, "\u0686\u0647\u0627\u0631": 4,
    "\u067e\u0646\u062c": 5, "\u0634\u0634": 6, "\u062f\u0647": 10,
    "\u067e\u0627\u0646\u0632\u062f\u0647": 15, "\u0633\u06cc": 30,
}

_ORDINALS: dict[str, int] = {
    "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4, "fifth": 5, "5th": 5, "last": 28,
    # Gloss: اول first, دوم second, سوم third, آخر last.
    "\u0627\u0648\u0644": 1, "\u062f\u0648\u0645": 2, "\u0633\u0648\u0645": 3,
    "\u0622\u062e\u0631": 28,
}


@dataclass(slots=True)
class _Parsed:
    minute: str = "0"
    hour: str = "0"
    day: str = "*"
    month: str = "*"
    weekday: str = "*"

    def to_cron(self) -> str:
        return f"{self.minute} {self.hour} {self.day} {self.month} {self.weekday}"


def _normalise(text: str) -> str:
    """Fold digits and scripts, then collapse punctuation and whitespace."""
    folded = normalize_fa(text or "")
    folded = folded.replace("\u060c", " ").replace(",", " ")
    folded = re.sub(r"[.\u061f?!]+", " ", folded)
    folded = folded.replace(":", ":").replace("\u06f1", "1")
    return re.sub(r"\s+", " ", folded).strip().lower()


def _find_count(text: str, units: tuple[str, ...]) -> int | None:
    """Read "every N <unit>", including spelled-out numbers.

    The Persian equivalent is "\u0647\u0631 N <unit>" ("every N <unit>").
    """
    for unit in units:
        # The count is optional ("every hour") and the unit may be plural
        # ("every 15 minutes"); Persian units take no plural suffix, so the
        # trailing ``s?`` is simply never used on that path.
        pattern = (
            rf"(?:{'|'.join(_EVERY)})\s+(\d+|[a-z\u0600-\u06ff ]+?)?\s*"
            rf"{re.escape(unit)}s?\b"
        )
        match = re.search(pattern, text)
        if not match:
            continue
        raw = (match.group(1) or "").strip()
        if raw.isdigit():
            return int(raw)
        for word, value in _NUMBER_WORDS.items():
            if raw.endswith(word):
                return value
        return 1  # bare "every hour"
    return None


def _read_time(text: str) -> tuple[int, int] | None:
    """Extract an explicit clock time, returning ``(hour, minute)``."""
    if any(word in text for word in _MIDNIGHT):
        return 0, 0
    # "12:30 noon" is a time with a qualifier, so only treat noon as 12:00 when
    # no digits accompany it.
    if any(word in text for word in _NOON) and not re.search(r"\d", text):
        return 12, 0

    match = re.search(r"(\d{1,2})\s*[:\u06f1]\s*(\d{2})", text) or re.search(
        r"(\d{1,2})\s*:\s*(\d{2})", text
    )
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    else:
        # A bare hour needs a marker so "every 15 minutes" is not read as 15:00.
        anchored = re.search(
            r"(?:at|@|\u0633\u0627\u0639\u062a)\s*(\d{1,2})(?!\s*\d)", text
        ) or re.search(r"\b(\d{1,2})\s*(?:am|pm|a\.m|p\.m)\b", text)
        if not anchored:
            return None
        hour, minute = int(anchored.group(1)), 0

    if hour > 23 or minute > 59:
        raise ScheduleParseError(f"invalid clock time in schedule: {hour}:{minute:02d}")

    # 12-hour disambiguation. Persian day-part words behave exactly as am/pm.
    if hour <= 12:
        if any(re.search(rf"(?<![a-z]){re.escape(w)}", text) for w in _AFTERNOON):
            if hour != 12:
                hour += 12
        elif any(re.search(rf"(?<![a-z]){re.escape(w)}", text) for w in _MORNING):
            if hour == 12:
                hour = 0
        elif any(word in text for word in _NOON) and hour == 12:
            hour = 12
    return hour, minute


def _read_weekday(text: str) -> str | None:
    """Extract a day-of-week field, if the text names one."""
    persian = _is_persian(text)
    if any(scope in text for scope in _WEEKDAY_SCOPE):
        return _IRANIAN_WORKDAYS if persian else "1-5"
    if any(scope in text for scope in _WEEKEND_SCOPE):
        return _IRANIAN_WEEKEND if persian else "0,6"
    found: list[int] = []
    for name in _WEEKDAY_ORDER:
        if name in ("sun", "mon", "tue", "wed", "thu", "fri", "sat"):
            hit = re.search(rf"\b{name}\b", text) is not None
        else:
            hit = name in text
        if hit and _WEEKDAYS[name] not in found:
            # Strip the match so "sunday" is not also counted as "sun".
            text = text.replace(name, " ")
            found.append(_WEEKDAYS[name])
    if not found:
        return None
    return ",".join(str(d) for d in sorted(found))


def _is_persian(text: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", text))


def _read_month_day(text: str) -> str | None:
    """Extract a day-of-month field from "first day of month" style phrasing."""
    monthly = any(word in text for word in _MONTH_WORDS)
    if not monthly:
        return None
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:day|\u0631\u0648\u0632)", text)
    if match and 1 <= int(match.group(1)) <= 31:
        return match.group(1)
    match = re.search(r"(?:day|\u0631\u0648\u0632)\s+(\d{1,2})", text)
    if match and 1 <= int(match.group(1)) <= 31:
        return match.group(1)
    for word, value in _ORDINALS.items():
        if re.search(rf"(?<![a-z\u0600-\u06ff]){re.escape(word)}(?![a-z\u0600-\u06ff])", text):
            return str(value)
    return "1"  # "every month" alone means the first of the month


def nl_to_cron(text: str) -> str:
    """Translate a natural-language schedule into a cron expression.

    :raises ScheduleParseError: when nothing matches. Guessing is worse than
        refusing: a schedule that fires at the wrong time is harder to notice
        than one that was never created.
    """
    original = text
    text = _normalise(text)
    if not text:
        raise ScheduleParseError("schedule text is empty")

    # A bare cron expression passes straight through, so one input box can take
    # either form without the user choosing a mode first.
    if re.fullmatch(r"[\d*/,\- ]+", text) and len(text.split()) == 5:
        from dream.cron import validate_cron

        return validate_cron(text)

    parsed = _Parsed()
    clock = _read_time(text)

    # 1. Sub-daily intervals. These own the minute and hour fields outright.
    minutes = _find_count(text, _MINUTE_WORDS)
    if minutes is not None:
        if not 1 <= minutes <= 59:
            raise ScheduleParseError(
                f"minute interval must be between 1 and 59, got {minutes}"
            )
        return _Parsed(minute=f"*/{minutes}" if minutes > 1 else "*", hour="*").to_cron()

    hours = _find_count(text, _HOUR_WORDS)
    # "every hour"/"هر ساعت" is an interval, but "هر روز ساعت ۹" uses ساعت as
    # the word "o'clock", so a clock reading wins over a bare hour interval.
    if hours is not None and not (clock is not None and hours == 1):
        if not 1 <= hours <= 23:
            raise ScheduleParseError(f"hour interval must be between 1 and 23, got {hours}")
        minute = str(clock[1]) if clock else "0"
        return _Parsed(minute=minute, hour=f"*/{hours}" if hours > 1 else "*").to_cron()

    # 2. Everything below fires at a specific time of day, defaulting to 00:00.
    if clock is not None:
        parsed.hour, parsed.minute = str(clock[0]), str(clock[1])

    # 3. Day scope, from most specific to least.
    weekday = _read_weekday(text)
    month_day = _read_month_day(text)
    day_interval = _find_count(text, _DAY_WORDS)

    if weekday is not None:
        parsed.weekday = weekday
    elif month_day is not None:
        parsed.day = month_day
        if any(word in text for word in _YEAR_WORDS):
            parsed.month = "1"
    elif any(word in text for word in _YEAR_WORDS):
        parsed.day, parsed.month = "1", "1"
    elif any(word in text for word in _WEEK_WORDS):
        parsed.weekday = "1"  # "weekly" with no named day means Monday
    elif day_interval is not None and day_interval > 1:
        parsed.day = f"*/{day_interval}"
    elif day_interval is not None or clock is not None:
        pass  # daily at the given time
    else:
        raise ScheduleParseError(
            f"could not understand schedule: {original.strip()!r}. "
            "Try phrasing such as 'every day at 9 AM' or 'every 15 minutes'."
        )

    return parsed.to_cron()


#: Documented examples, exercised verbatim by the test suite and shown in the
#: UI as placeholder hints.
NL_EXAMPLES: tuple[tuple[str, str], ...] = (
    ("every day at 9 AM", "0 9 * * *"),
    ("every weekday at 6 PM", "0 18 * * 1-5"),
    ("every monday at 10:30", "30 10 * * 1"),
    ("every 2 hours", "0 */2 * * *"),
    ("every first day of month", "0 0 1 * *"),
    ("every 15 minutes", "*/15 * * * *"),
    # Gloss: هر روز ساعت ۹ صبح — every day at 9 AM.
    ("\u0647\u0631 \u0631\u0648\u0632 \u0633\u0627\u0639\u062a \u06f9 \u0635\u0628\u062d",
     "0 9 * * *"),
)
