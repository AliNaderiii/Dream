"""A small five-field cron parser, matcher and next-fire calculator.

Dream schedules are stored as standard cron expressions because that is the
format users can read, edit and paste elsewhere. Only the classic five fields
are supported — minute, hour, day-of-month, month, day-of-week — with ``*``,
``*/n``, ``a-b``, ``a-b/n`` and comma lists. No seconds field, no ``@hourly``
aliases, no ``L``/``W``/``#`` extensions: the scheduler polls every thirty
seconds, so sub-minute precision would be a promise it cannot keep.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

__all__ = [
    "CRON_FIELDS",
    "CronExpression",
    "cron_matches",
    "describe_cron",
    "next_run_after",
    "parse_cron",
    "validate_cron",
]

#: ``(name, minimum, maximum)`` per field, in wire order.
CRON_FIELDS: tuple[tuple[str, int, int], ...] = (
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("weekday", 0, 6),
)

_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_WEEKDAY_NAMES = (
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
)

#: Four years of minutes is the bound on the forward walk in
#: :func:`next_run_after`. It comfortably covers the longest real schedule (29
#: February, which recurs at most every four years) while guaranteeing that an
#: impossible expression such as ``0 0 30 2 *`` terminates.
_SEARCH_LIMIT_DAYS = 366 * 4


@dataclass(frozen=True, slots=True)
class CronExpression:
    """A parsed cron expression as five sets of permitted values."""

    expression: str
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    day_restricted: bool
    weekday_restricted: bool

    def matches(self, moment: datetime) -> bool:
        """Whether ``moment`` (to the minute) satisfies this expression."""
        if moment.minute not in self.minutes or moment.hour not in self.hours:
            return False
        if moment.month not in self.months:
            return False
        # Vixie cron: when both day-of-month and day-of-week are restricted the
        # expression fires on either, not on their intersection. "1st of the
        # month and every Monday" must not silently mean "Monday the 1st".
        day_ok = moment.day in self.days
        weekday_ok = ((moment.weekday() + 1) % 7) in self.weekdays
        if self.day_restricted and self.weekday_restricted:
            return day_ok or weekday_ok
        return day_ok and weekday_ok


def _parse_field(raw: str, name: str, low: int, high: int) -> tuple[frozenset[int], bool]:
    """Expand one field to its value set and whether it is restricted."""
    raw = raw.strip()
    if not raw:
        raise ValueError(f"cron {name} field is empty")
    values: set[int] = set()
    restricted = False
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"cron {name} field has an empty list item")
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            try:
                step = int(step_text)
            except ValueError:
                raise ValueError(
                    f"cron {name} step must be an integer, got {step_text!r}"
                ) from None
            if step < 1:
                raise ValueError(f"cron {name} step must be positive, got {step}")
        if part in ("*", ""):
            start, end = low, high
            if step != 1:
                restricted = True
        elif "-" in part.lstrip("-"):
            start_text, _, end_text = part.partition("-")
            start, end = _int(start_text, name), _int(end_text, name)
            restricted = True
        else:
            start = end = _int(part, name)
            restricted = True
        if name == "weekday":
            # Both 0 and 7 mean Sunday in every cron dialect worth matching.
            start, end = (0 if start == 7 else start), (0 if end == 7 else end)
            if end < start:
                # A wrapping range such as fri-mon (5-1).
                values.update(range(start, 7, step))
                values.update(range(0, end + 1, step))
                continue
        if start < low or end > high or end < start:
            raise ValueError(f"cron {name} value out of range [{low}, {high}]: {part!r}")
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"cron {name} field matches nothing: {raw!r}")
    return frozenset(values), restricted


def _int(text: str, field: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError(f"cron {field} value must be an integer, got {text.strip()!r}") from None


def parse_cron(expression: str) -> CronExpression:
    """Parse a five-field cron expression, raising ``ValueError`` if invalid."""
    if not isinstance(expression, str):
        raise ValueError("cron expression must be a string")
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError(
            f"cron expression must have 5 fields (minute hour day month weekday), "
            f"got {len(fields)}: {expression!r}"
        )
    parsed: list[frozenset[int]] = []
    restrictions: list[bool] = []
    for raw, (name, low, high) in zip(fields, CRON_FIELDS, strict=True):
        values, restricted = _parse_field(raw, name, low, high)
        parsed.append(values)
        restrictions.append(restricted)
    return CronExpression(
        expression=" ".join(fields),
        minutes=parsed[0],
        hours=parsed[1],
        days=parsed[2],
        months=parsed[3],
        weekdays=parsed[4],
        day_restricted=restrictions[2],
        weekday_restricted=restrictions[4],
    )


def validate_cron(expression: str) -> str:
    """Return the normalised expression, or raise ``ValueError``."""
    return parse_cron(expression).expression


def cron_matches(expression: str | CronExpression, moment: datetime) -> bool:
    """Whether a cron expression fires at ``moment``."""
    parsed = expression if isinstance(expression, CronExpression) else parse_cron(expression)
    return parsed.matches(moment)


def next_run_after(expression: str | CronExpression, after: datetime) -> datetime:
    """The first minute strictly after ``after`` at which the expression fires.

    Walks forward a minute at a time, skipping whole days when the date fields
    cannot match, which keeps even a yearly schedule well under a millisecond.
    """
    parsed = expression if isinstance(expression, CronExpression) else parse_cron(expression)
    moment = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    limit = after + timedelta(days=_SEARCH_LIMIT_DAYS)
    while moment <= limit:
        if not _date_could_match(parsed, moment):
            moment = (moment + timedelta(days=1)).replace(hour=0, minute=0)
            continue
        if parsed.matches(moment):
            return moment
        moment += timedelta(minutes=1)
    raise ValueError(f"cron expression never fires: {parsed.expression!r}")


def _date_could_match(parsed: CronExpression, moment: datetime) -> bool:
    if moment.month not in parsed.months:
        return False
    day_ok = moment.day in parsed.days
    weekday_ok = ((moment.weekday() + 1) % 7) in parsed.weekdays
    if parsed.day_restricted and parsed.weekday_restricted:
        return day_ok or weekday_ok
    return day_ok and weekday_ok


# --------------------------------------------------------------------------
# Human-readable rendering
# --------------------------------------------------------------------------


def _ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def _clock(hour: int, minute: int) -> str:
    suffix = "AM" if hour < 12 else "PM"
    display = hour % 12 or 12
    return f"{display}:{minute:02d} {suffix}"


def _step_of(field: str) -> int | None:
    if field.startswith("*/"):
        try:
            return int(field[2:])
        except ValueError:
            return None
    return None


def _weekday_phrase(field: str, weekdays: frozenset[int]) -> str:
    if field == "1-5":
        return "every weekday"
    if field in ("0,6", "6,0", "6,7", "0,6,7"):
        return "every weekend day"
    if field == "6,0,1,2,3":
        return "every Iranian working day (Sat–Wed)"
    names = [_WEEKDAY_NAMES[d] for d in sorted(weekdays)]
    if len(names) == 1:
        return f"every {names[0]}"
    return "every " + ", ".join(names[:-1]) + f" and {names[-1]}"


def describe_cron(expression: str) -> str:
    """Render a cron expression as an English sentence for the UI.

    Covers the shapes :func:`dream.scheduler.nl_to_cron` can emit precisely,
    and degrades to a field-by-field reading for anything hand-written.
    """
    parsed = parse_cron(expression)
    minute_f, hour_f, day_f, month_f, weekday_f = parsed.expression.split()

    minute_step = _step_of(minute_f)
    if minute_step and hour_f == "*" and day_f == "*" and month_f == "*" and weekday_f == "*":
        unit = "minute" if minute_step == 1 else "minutes"
        return f"every {minute_step} {unit}"

    hour_step = _step_of(hour_f)
    if hour_step and day_f == "*" and month_f == "*" and weekday_f == "*":
        minutes = sorted(parsed.minutes)
        at = "" if minutes == [0] else f" at {minutes[0]} past"
        unit = "hour" if hour_step == 1 else "hours"
        return f"every {hour_step} {unit}{at}"

    day_step = _step_of(day_f)
    if day_step and month_f == "*" and weekday_f == "*" and len(parsed.hours) == 1:
        hour = next(iter(parsed.hours))
        minute = min(parsed.minutes)
        unit = "day" if day_step == 1 else "days"
        return f"every {day_step} {unit} at {_clock(hour, minute)}"

    if minute_f == "*" and hour_f == "*":
        return "every minute"

    if len(parsed.hours) != 1 or len(parsed.minutes) != 1:
        return f"at cron schedule {parsed.expression}"

    at = _clock(next(iter(parsed.hours)), next(iter(parsed.minutes)))

    if weekday_f != "*":
        when = _weekday_phrase(weekday_f, parsed.weekdays)
    elif day_f != "*":
        days = " and ".join(_ordinal(d) for d in sorted(parsed.days))
        when = f"on the {days}"
    else:
        when = "every day"

    if month_f != "*":
        months = " and ".join(_MONTH_NAMES[m - 1] for m in sorted(parsed.months))
        when = f"{when} in {months}"

    return f"{when} at {at}"
