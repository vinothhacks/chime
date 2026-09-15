"""Pure scheduler. Injected clock only — never datetime.now()."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from chime.clock import ensure_aware_utc
from chime.models import Alarm, Decision, Occurrence, ScheduleKind, Snooze
from chime.time_utils import occurrence_on_date


def next_occurrence(alarm: Alarm, now: datetime) -> Occurrence | None:
    """Soonest valid occurrence at or after `now`."""
    now_utc = ensure_aware_utc(now)
    if not alarm.enabled:
        return None
    day = now_utc.astimezone(ZoneInfo(alarm.timezone)).date()
    for _ in range(400):
        if _date_matches(alarm, day):
            occ = occurrence_on_date(alarm, day)
            if occ is not None and occ.scheduled_utc >= now_utc:
                return occ
        day += timedelta(days=1)
    return None


def occurrences_between(alarm: Alarm, start: datetime, end: datetime) -> list[Occurrence]:
    """Valid occurrences with scheduled_utc in [start, end]."""
    start_utc = ensure_aware_utc(start)
    end_utc = ensure_aware_utc(end)
    tz = ZoneInfo(alarm.timezone)
    day = start_utc.astimezone(tz).date() - timedelta(days=1)
    last = end_utc.astimezone(tz).date() + timedelta(days=1)
    found: list[Occurrence] = []
    while day <= last:
        if _date_matches(alarm, day):
            occ = occurrence_on_date(alarm, day)
            if occ is not None and start_utc <= occ.scheduled_utc <= end_utc:
                found.append(occ)
        day += timedelta(days=1)
    return found


def evaluate_occurrence(
    occurrence: Occurrence,
    now: datetime,
    grace: timedelta,
    claimed_keys: set[str],
) -> Decision:
    now_utc = ensure_aware_utc(now)
    if occurrence.key in claimed_keys:
        return Decision.ALREADY_CLAIMED
    if now_utc < occurrence.scheduled_utc:
        return Decision.NOT_DUE
    if now_utc - occurrence.scheduled_utc <= grace:
        return Decision.RING
    return Decision.MISSED


def evaluate_snoozes(snoozes: Sequence[Snooze], now: datetime) -> list[Snooze]:
    now_utc = ensure_aware_utc(now)
    return [item for item in snoozes if item.until_utc <= now_utc]


def _date_matches(alarm: Alarm, day: date) -> bool:
    if alarm.kind is ScheduleKind.ONCE:
        return True
    return day.weekday() in {int(item) for item in alarm.days}
