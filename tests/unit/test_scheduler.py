from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from chime.clock import FakeClock
from chime.models import Alarm, Decision, ScheduleKind, Snooze, Weekday
from chime.scheduler import evaluate_occurrence, evaluate_snoozes, next_occurrence
from chime.time_utils import occurrence_on_date


def _weekly(time: str, days: set[Weekday], tz: str = "UTC") -> Alarm:
    return Alarm(
        id="abcd1234",
        local_time=time,
        timezone=tz,
        kind=ScheduleKind.WEEKLY,
        days=frozenset(days),
        label="Gym",
    )


def test_exact_time_rings() -> None:
    alarm = _weekly("07:30", {Weekday.TUE}, "Asia/Kolkata")
    now = datetime(2026, 9, 15, 7, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
    occ = next_occurrence(alarm, now)
    assert occ is not None
    decision = evaluate_occurrence(occ, now, timedelta(minutes=5), set())
    assert decision is Decision.RING


def test_one_second_before_not_due() -> None:
    alarm = _weekly("07:30", {Weekday.TUE}, "Asia/Kolkata")
    now = datetime(2026, 9, 15, 7, 29, 59, tzinfo=ZoneInfo("Asia/Kolkata"))
    occ = next_occurrence(alarm, now)
    assert occ is not None
    assert evaluate_occurrence(occ, now, timedelta(minutes=5), set()) is Decision.NOT_DUE


def test_one_second_after_rings() -> None:
    alarm = _weekly("07:30", {Weekday.TUE}, "Asia/Kolkata")
    now = datetime(2026, 9, 15, 7, 30, 1, tzinfo=ZoneInfo("Asia/Kolkata"))
    occ = occurrence_on_date(alarm, now.date())
    assert occ is not None
    assert evaluate_occurrence(occ, now, timedelta(minutes=5), set()) is Decision.RING


def test_grace_boundary_inclusive() -> None:
    alarm = _weekly("07:30", {Weekday.TUE}, "UTC")
    occ = occurrence_on_date(alarm, datetime(2026, 9, 15).date())
    assert occ is not None
    at_grace = occ.scheduled_utc + timedelta(minutes=5)
    assert evaluate_occurrence(occ, at_grace, timedelta(minutes=5), set()) is Decision.RING
    outside = occ.scheduled_utc + timedelta(minutes=5, seconds=1)
    assert evaluate_occurrence(occ, outside, timedelta(minutes=5), set()) is Decision.MISSED


def test_already_claimed() -> None:
    alarm = _weekly("07:30", {Weekday.TUE}, "UTC")
    occ = occurrence_on_date(alarm, datetime(2026, 9, 15).date())
    assert occ is not None
    now = occ.scheduled_utc + timedelta(seconds=1)
    assert (
        evaluate_occurrence(occ, now, timedelta(minutes=5), {occ.key}) is Decision.ALREADY_CLAIMED
    )


def test_disabled_has_no_next() -> None:
    alarm = Alarm(
        id="x",
        local_time="07:30",
        timezone="UTC",
        kind=ScheduleKind.ONCE,
        days=frozenset(),
        enabled=False,
    )
    now = datetime(2026, 9, 15, 6, 0, tzinfo=ZoneInfo("UTC"))
    assert next_occurrence(alarm, now) is None


def test_weekdays_skips_saturday() -> None:
    alarm = _weekly(
        "08:00",
        {Weekday.MON, Weekday.TUE, Weekday.WED, Weekday.THU, Weekday.FRI},
        "UTC",
    )
    saturday = datetime(2026, 9, 19, 9, 0, tzinfo=ZoneInfo("UTC"))
    occ = next_occurrence(alarm, saturday)
    assert occ is not None
    assert occ.scheduled_local.weekday() == Weekday.MON


def test_spring_forward_skips_to_next_week() -> None:
    alarm = _weekly("02:30", {Weekday.SUN}, "America/New_York")
    now = datetime(2026, 3, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))
    occ = next_occurrence(alarm, now)
    assert occ is not None
    assert occ.scheduled_local.date().isoformat() == "2026-03-15"


def test_fall_back_fires_once() -> None:
    alarm = _weekly("01:30", {Weekday.SUN}, "America/New_York")
    now = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"))
    occ = next_occurrence(alarm, now)
    assert occ is not None
    assert occ.fold == 0
    claimed = {occ.key}
    later = occ.scheduled_utc + timedelta(hours=1)
    assert (
        evaluate_occurrence(occ, later, timedelta(minutes=5), claimed) is Decision.ALREADY_CLAIMED
    )


def test_year_rollover() -> None:
    alarm = _weekly("00:05", {Weekday.FRI}, "UTC")
    now = datetime(2026, 12, 31, 23, 0, tzinfo=ZoneInfo("UTC"))
    occ = next_occurrence(alarm, now)
    assert occ is not None
    assert occ.scheduled_local.year == 2027


def test_leap_day() -> None:
    alarm = Alarm(
        id="leap",
        local_time="09:00",
        timezone="UTC",
        kind=ScheduleKind.ONCE,
        days=frozenset(),
    )
    now = datetime(2028, 2, 29, 8, 0, tzinfo=ZoneInfo("UTC"))
    occ = next_occurrence(alarm, now)
    assert occ is not None
    assert occ.scheduled_local.date().isoformat() == "2028-02-29"


def test_backward_clock_jump_does_not_unclaim() -> None:
    alarm = _weekly("07:30", {Weekday.TUE}, "UTC")
    occ = occurrence_on_date(alarm, datetime(2026, 9, 15).date())
    assert occ is not None
    claimed = {occ.key}
    earlier = occ.scheduled_utc - timedelta(hours=1)
    assert (
        evaluate_occurrence(occ, earlier, timedelta(minutes=5), claimed) is Decision.ALREADY_CLAIMED
    )


def test_snoozes_due() -> None:
    now = datetime(2026, 9, 15, 8, 0, tzinfo=ZoneInfo("UTC"))
    due = Snooze("s1", "a1", now - timedelta(seconds=1), 1)
    pending = Snooze("s2", "a1", now + timedelta(minutes=9), 2)
    assert evaluate_snoozes([due, pending], now) == [due]


def test_fake_clock_advance() -> None:
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, tzinfo=ZoneInfo("UTC")))
    clock.advance(90)
    assert clock.now_utc().minute == 1
    assert clock.now_utc().second == 30
