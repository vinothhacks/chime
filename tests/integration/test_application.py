from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from chime.application import Application
from chime.clock import FakeClock
from chime.errors import ValidationError
from chime.models import ScheduleKind


def test_create_list_toggle_delete(app: Application) -> None:
    once = app.create_alarm("07:30", once=True, label="Gym")
    weekly = app.create_alarm("08:15", days_raw="sat,sun", label="Weekend")
    weekdays = app.create_alarm("22:00", days_raw="weekdays", label="Wind down")
    alarms = app.list_alarms()
    assert len(alarms) == 3
    assert once.kind is ScheduleKind.ONCE
    assert weekly.days
    assert len(weekdays.days) == 5
    app.set_alarm_enabled(weekly.id, False)
    assert app.list_alarms()[1].enabled is False
    app.delete_alarm(once.id)
    assert len(app.list_alarms()) == 2


def test_ring_once_and_restart_does_not_rerun(app: Application, clock: FakeClock) -> None:
    alarm = app.create_alarm("07:30", once=True, label="Gym", timezone="Asia/Kolkata")
    clock.set(datetime(2026, 9, 15, 7, 30, tzinfo=ZoneInfo("Asia/Kolkata")))
    first = app.process_clock_tick()
    assert first.ring is not None
    assert first.ring.alarm_id == alarm.id
    key = first.ring.occurrence_key
    app.dismiss_active_ring()
    second = app.process_clock_tick()
    assert second.ring is None
    claimed = {item.key for item in second.state.runtime.claimed_occurrences}
    assert key in claimed
    assert app.list_alarms()[0].enabled is False


def test_grace_two_minutes_late_rings(app: Application, clock: FakeClock) -> None:
    app.create_alarm("07:30", once=True, timezone="Asia/Kolkata")
    clock.set(datetime(2026, 9, 15, 7, 32, tzinfo=ZoneInfo("Asia/Kolkata")))
    result = app.process_clock_tick()
    assert result.ring is not None


def test_sixty_minutes_late_is_missed(app: Application, clock: FakeClock) -> None:
    alarm = app.create_alarm("07:30", once=True, timezone="Asia/Kolkata")
    clock.set(datetime(2026, 9, 15, 8, 30, tzinfo=ZoneInfo("Asia/Kolkata")))
    result = app.process_clock_tick()
    assert result.ring is None
    assert result.missed_keys
    assert app.list_alarms()[0].enabled is False
    occ_key = result.missed_keys[0]
    assert alarm.id in occ_key


def test_snooze_max_then_reject(app: Application, clock: FakeClock) -> None:
    app.create_alarm("07:30", once=True, timezone="UTC", snooze_minutes=9, max_snoozes=3)
    clock.set(datetime(2026, 9, 15, 7, 30, tzinfo=UTC))
    assert app.process_clock_tick().ring is not None
    for _ in range(3):
        snooze = app.snooze_active_ring()
        clock.set(snooze.until_utc)
        tick = app.process_clock_tick()
        assert tick.ring is not None
        assert tick.snooze_ring is True
    with pytest.raises(ValidationError, match="maximum snoozes"):
        app.snooze_active_ring()


def test_forward_clock_jump_misses(app: Application, clock: FakeClock) -> None:
    app.create_alarm("07:30", days_raw="tue", timezone="UTC")
    clock.set(datetime(2026, 9, 15, 10, 0, tzinfo=UTC))
    result = app.process_clock_tick()
    assert result.ring is None
    assert result.missed_keys


def test_claim_before_ring_persisted(app: Application, clock: FakeClock, store) -> None:
    app.create_alarm("07:30", once=True, timezone="UTC")
    clock.set(datetime(2026, 9, 15, 7, 30, tzinfo=UTC))
    result = app.process_clock_tick()
    assert result.ring is not None
    reloaded = store.load()
    keys = {item.key for item in reloaded.runtime.claimed_occurrences}
    assert result.ring.occurrence_key in keys
    assert reloaded.runtime.active_ring is not None
