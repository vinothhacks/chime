from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from chime.errors import ValidationError
from chime.models import Alarm, ScheduleKind, Weekday
from chime.time_utils import (
    is_ambiguous,
    is_nonexistent,
    occurrence_on_date,
    parse_days,
    parse_local_time,
    validate_timezone,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("07:30", "07:30"),
        ("7:30", "07:30"),
        ("730", "07:30"),
        ("7:30pm", "19:30"),
        ("12:00am", "00:00"),
        ("12:00pm", "12:00"),
    ],
)
def test_parse_local_time(raw: str, expected: str) -> None:
    assert parse_local_time(raw) == expected


@pytest.mark.parametrize("raw", ["", "24:00", "7:60", "abc", "13:00pm"])
def test_parse_local_time_rejects(raw: str) -> None:
    with pytest.raises(ValidationError):
        parse_local_time(raw)


def test_parse_days_aliases() -> None:
    assert parse_days("weekdays") == frozenset(
        {Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU, Weekday.FRI}
    )
    assert parse_days("sat,sun") == frozenset({Weekday.SAT, Weekday.SUN})
    assert parse_days("weekends") == frozenset({Weekday.SAT, Weekday.SUN})
    assert parse_days("weekdays,sat,sun") == frozenset(Weekday)


def test_validate_timezone() -> None:
    assert validate_timezone("Asia/Kolkata") == "Asia/Kolkata"
    with pytest.raises(ValidationError):
        validate_timezone("Not/AZone")


def test_spring_forward_nonexistent() -> None:
    naive = datetime(2026, 3, 8, 2, 30)
    tz = ZoneInfo("America/New_York")
    assert is_nonexistent(naive, tz)
    alarm = Alarm(
        id="a1",
        local_time="02:30",
        timezone="America/New_York",
        kind=ScheduleKind.WEEKLY,
        days=frozenset({Weekday.SUN}),
    )
    assert occurrence_on_date(alarm, date(2026, 3, 8)) is None


def test_fall_back_ambiguous_uses_fold_zero() -> None:
    naive = datetime(2026, 11, 1, 1, 30)
    tz = ZoneInfo("America/New_York")
    assert is_ambiguous(naive, tz)
    alarm = Alarm(
        id="a1",
        local_time="01:30",
        timezone="America/New_York",
        kind=ScheduleKind.WEEKLY,
        days=frozenset({Weekday.SUN}),
    )
    occ = occurrence_on_date(alarm, date(2026, 11, 1))
    assert occ is not None
    assert occ.fold == 0
    assert occ.key.endswith(":01:30:0")
