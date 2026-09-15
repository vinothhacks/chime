from __future__ import annotations

from datetime import datetime

from textual.widgets import Digits


class BigClock(Digits):
    def update_now(self, local_now: datetime, format_24h: bool) -> None:
        if format_24h:
            self.update(local_now.strftime("%H:%M:%S"))
        else:
            self.update(local_now.strftime("%I:%M:%S %p").lstrip("0"))
