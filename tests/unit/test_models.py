from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from chime.models import Alarm, Occurrence, ScheduleKind, Weekday


def test_occurrence_key_includes_fold() -> None:
    local = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"))
    occ = Occurrence(
        alarm_id="ab12cd34",
        scheduled_local=local,
        scheduled_utc=local.astimezone(UTC),
        fold=0,
    )
    assert occ.key == "ab12cd34:2026-11-01:01:30:0"


def test_weekly_requires_days_in_constructor_shape() -> None:
    alarm = Alarm(
        id="x",
        local_time="07:30",
        timezone="UTC",
        kind=ScheduleKind.WEEKLY,
        days=frozenset({Weekday.MON}),
    )
    assert alarm.kind is ScheduleKind.WEEKLY
    assert Weekday.MON in alarm.days
