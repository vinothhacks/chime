from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import ListItem, ListView

from chime.tui.widgets.alarm_row import AlarmRow

if TYPE_CHECKING:
    from chime.models import Alarm


class AlarmListItem(ListItem):
    def __init__(self, alarm: Alarm, format_24h: bool) -> None:
        super().__init__(AlarmRow(alarm, format_24h))
        self.alarm = alarm


class AlarmList(ListView):
    def set_alarms(self, alarms: tuple[Alarm, ...], format_24h: bool) -> None:
        self.clear()
        for alarm in alarms:
            self.append(AlarmListItem(alarm, format_24h))
