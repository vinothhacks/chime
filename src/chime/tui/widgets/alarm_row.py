from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label

from chime.models import Alarm, ScheduleKind


def day_marks(alarm: Alarm) -> str:
    if alarm.kind is ScheduleKind.ONCE:
        return "once"
    names = ["M", "T", "W", "T", "F", "S", "S"]
    enabled = {int(day) for day in alarm.days}
    return " ".join(name if idx in enabled else "." for idx, name in enumerate(names))


def format_hhmm(hhmm: str, format_24h: bool) -> str:
    hour, minute = (int(part) for part in hhmm.split(":"))
    if format_24h:
        return f"{hour:02d}:{minute:02d}"
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {suffix}"


class AlarmRow(Widget):
    def __init__(self, alarm: Alarm, format_24h: bool = True) -> None:
        super().__init__()
        self.alarm = alarm
        self.format_24h = format_24h

    def compose(self) -> ComposeResult:
        alarm = self.alarm
        state = "ON" if alarm.enabled else "OFF"
        state_class = "state-on" if alarm.enabled else "state-off"
        label = alarm.label or "(no label)"
        if len(label) > 28:
            label = label[:27] + "…"
        yield Label(format_hhmm(alarm.local_time, self.format_24h), classes="time")
        yield Label(day_marks(alarm), classes="days")
        yield Label(label, classes="label")
        yield Label(f"[{state}]", classes=state_class)
