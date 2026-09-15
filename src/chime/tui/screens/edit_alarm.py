from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static, Switch

from chime.models import Alarm, ScheduleKind


class EditAlarmScreen(ModalScreen[dict[str, str] | None]):
    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, alarm: Alarm | None = None) -> None:
        super().__init__()
        self.alarm = alarm

    def compose(self) -> ComposeResult:
        alarm = self.alarm
        time_value = alarm.local_time if alarm else ""
        label_value = alarm.label if alarm else ""
        snooze_value = str(alarm.snooze_minutes if alarm else 9)
        max_value = str(alarm.max_snoozes if alarm else 3)
        once = True if alarm is None else alarm.kind is ScheduleKind.ONCE
        days_value = ""
        if alarm is not None and alarm.kind is ScheduleKind.WEEKLY:
            days_value = ",".join(day.name.lower() for day in sorted(alarm.days, key=int))
        with Vertical(id="edit-box"):
            yield Label("Edit alarm" if alarm else "Add alarm")
            yield Label("Time")
            yield Input(time_value, placeholder="07:30", id="time")
            yield Label("Label")
            yield Input(label_value, placeholder="Gym", id="label")
            yield Horizontal(
                Label("One-shot"),
                Switch(value=once, id="once"),
            )
            yield Label("Days (weekdays / sat,sun) — ignored for one-shot")
            yield Input(days_value, placeholder="weekdays", id="days")
            yield Label("Snooze minutes")
            yield Input(snooze_value, id="snooze")
            yield Label("Max snoozes")
            yield Input(max_value, id="max_snoozes")
            yield Static("", id="edit-error")
            yield Horizontal(
                Button("Save", variant="primary", id="save"),
                Button("Cancel", id="cancel"),
            )

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "save":
            self._submit()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        error = self.query_one("#edit-error", Static)
        payload = {
            "time": self.query_one("#time", Input).value,
            "label": self.query_one("#label", Input).value,
            "once": "1" if self.query_one("#once", Switch).value else "0",
            "days": self.query_one("#days", Input).value,
            "timezone": "Asia/Kolkata",
            "snooze": self.query_one("#snooze", Input).value,
            "max_snoozes": self.query_one("#max_snoozes", Input).value,
        }
        if not payload["time"].strip():
            error.update("time is required")
            return
        try:
            snooze = int(payload["snooze"])
            max_snoozes = int(payload["max_snoozes"])
        except ValueError:
            error.update("snooze fields must be integers")
            return
        if not 1 <= snooze <= 60 or not 0 <= max_snoozes <= 9:
            error.update("snooze 1-60 minutes, max snoozes 0-9")
            return
        self.dismiss(payload)
