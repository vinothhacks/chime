from __future__ import annotations

from datetime import datetime

from textual.widgets import Static

from chime.models import Alarm, Occurrence


class NextAlarm(Static):
    def show(self, occurrence: Occurrence | None, alarms: tuple[Alarm, ...], now: datetime) -> None:
        if occurrence is None:
            self.update("Next: none")
            return
        alarm = next((item for item in alarms if item.id == occurrence.alarm_id), None)
        label = (alarm.label if alarm else "") or "alarm"
        remaining = occurrence.scheduled_utc - now
        total = int(max(remaining.total_seconds(), 0))
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        self.update(f"Next: {label} in {hours:02d}:{minutes:02d}:{seconds:02d}")
