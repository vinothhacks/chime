"""Wall-clock parsing, DST helpers, weekday aliases. No framework imports."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from chime.errors import ValidationError
from chime.models import Alarm, Occurrence, Weekday

_WEEKDAY_NAMES: dict[str, Weekday] = {
    "mon": Weekday.MON,
    "monday": Weekday.MON,
    "tue": Weekday.TUE,
    "tues": Weekday.TUE,
    "tuesday": Weekday.TUE,
    "wed": Weekday.WED,
    "wednesday": Weekday.WED,
    "thu": Weekday.THU,
    "thur": Weekday.THU,
    "thurs": Weekday.THU,
    "thursday": Weekday.THU,
    "fri": Weekday.FRI,
    "friday": Weekday.FRI,
    "sat": Weekday.SAT,
    "saturday": Weekday.SAT,
    "sun": Weekday.SUN,
    "sunday": Weekday.SUN,
}


def parse_local_time(raw: str) -> str:
    """Accept 07:30, 7:30, 730, 7:30pm. Return HH:MM (24h)."""
    s = raw.strip().lower().replace(" ", "")
    if not s:
        raise ValidationError("time is required")
    ampm: str | None = None
    if s.endswith(("am", "pm")):
        ampm = s[-2:]
        s = s[:-2]
    hour: int
    minute: int
    if ":" in s:
        parts = s.split(":")
        if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
            raise ValidationError(f"invalid time: {raw}")
        hour, minute = int(parts[0]), int(parts[1])
    elif s.isdigit() and len(s) in (3, 4):
        if len(s) == 3:
            hour, minute = int(s[0]), int(s[1:])
        else:
            hour, minute = int(s[:2]), int(s[2:])
    else:
        raise ValidationError(f"invalid time: {raw}")
    if ampm is not None:
        if hour < 1 or hour > 12:
            raise ValidationError(f"invalid time: {raw}")
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = hour if hour == 12 else hour + 12
    if hour > 23 or minute > 59:
        raise ValidationError(f"invalid time: {raw}")
    return f"{hour:02d}:{minute:02d}"


def parse_days(raw: str) -> frozenset[Weekday]:
    s = raw.strip().lower()
    if not s:
        raise ValidationError("at least one weekday is required")
    if s in {"weekdays", "weekday"}:
        return frozenset({Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU, Weekday.FRI})
    if s in {"weekends", "weekend"}:
        return frozenset({Weekday.SAT, Weekday.SUN})
    if s in {"everyday", "every-day", "all"}:
        return frozenset(Weekday)
    days: set[Weekday] = set()
    for token in re.split(r"[,\s]+", s):
        if not token:
            continue
        if token in {"weekdays", "weekday"}:
            days.update(
                {Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU, Weekday.FRI}
            )
            continue
        if token in {"weekends", "weekend"}:
            days.update({Weekday.SAT, Weekday.SUN})
            continue
        if token in {"everyday", "every-day", "all"}:
            days.update(Weekday)
            continue
        day = _WEEKDAY_NAMES.get(token)
        if day is None:
            raise ValidationError(f"unknown weekday: {token}")
        days.add(day)
    if not days:
        raise ValidationError("at least one weekday is required")
    return frozenset(days)


def validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(f"unknown timezone: {name}") from exc
    return name


def is_nonexistent(naive_local: datetime, tz: ZoneInfo) -> bool:
    """True when the local wall time does not exist (spring forward)."""
    if naive_local.tzinfo is not None:
        raise ValidationError("expected naive local datetime")
    folded = naive_local.replace(tzinfo=tz, fold=0)
    back = folded.astimezone(UTC).astimezone(tz)
    return back.replace(tzinfo=None) != naive_local.replace(tzinfo=None, microsecond=0)


def is_ambiguous(naive_local: datetime, tz: ZoneInfo) -> bool:
    if naive_local.tzinfo is not None:
        raise ValidationError("expected naive local datetime")
    a = naive_local.replace(tzinfo=tz, fold=0)
    b = naive_local.replace(tzinfo=tz, fold=1)
    return a.utcoffset() != b.utcoffset()


def occurrence_on_date(alarm: Alarm, day: date) -> Occurrence | None:
    """Build the occurrence for `day` at the alarm's local time.

    Nonexistent local times return None (skip). Ambiguous times use fold=0.
    """
    hour, minute = (int(p) for p in alarm.local_time.split(":"))
    naive = datetime(day.year, day.month, day.day, hour, minute)
    tz = ZoneInfo(alarm.timezone)
    if is_nonexistent(naive, tz):
        return None
    fold = 0
    aware = naive.replace(tzinfo=tz, fold=fold)
    return Occurrence(
        alarm_id=alarm.id,
        scheduled_local=aware,
        scheduled_utc=aware.astimezone(UTC),
        fold=fold,
    )
