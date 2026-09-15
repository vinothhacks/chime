from __future__ import annotations

from datetime import UTC, datetime

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from chime.models import ActiveRing, Alarm
from chime.sound import AudioPlayer, DefaultAudioPlayer
from chime.tui.widgets.alarm_row import format_hhmm


class RingingScreen(ModalScreen[str]):
    """Result: snooze | dismiss."""

    BINDINGS = [
        ("s", "ring_snooze", "Snooze"),
        ("d", "ring_dismiss", "Dismiss"),
        ("q", "ring_dismiss", "Dismiss"),
    ]

    def __init__(
        self,
        ring: ActiveRing,
        alarm: Alarm,
        format_24h: bool,
        started: datetime,
        audio: AudioPlayer | None = None,
    ) -> None:
        super().__init__()
        self.ring = ring
        self.alarm = alarm
        self.format_24h = format_24h
        self.started = started
        self.audio = audio if audio is not None else DefaultAudioPlayer()

    def compose(self) -> ComposeResult:
        with Vertical(id="ring-box"):
            yield Static("ALARM", id="ring-title")
            yield Static(format_hhmm(self.alarm.local_time, self.format_24h), id="ring-time")
            yield Static(self.alarm.label or "", id="ring-label")
            yield Static("Ringing for 00:00:00", id="ring-elapsed")
            yield Static("[S] Snooze      [D] Dismiss", id="ring-keys")

    async def on_mount(self) -> None:
        try:
            await self.audio.start("default")
        except Exception:
            pass
        self.set_interval(0.5, self._pulse)
        self.set_interval(1.0, self._elapsed)

    async def on_unmount(self) -> None:
        try:
            await self.audio.stop()
        except Exception:
            pass

    def _pulse(self) -> None:
        box = self.query_one("#ring-box")
        box.set_class(not box.has_class("pulse"), "pulse")

    def _elapsed(self) -> None:
        now = datetime.now(UTC)
        seconds = int(max((now - self.started).total_seconds(), 0))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        self.query_one("#ring-elapsed", Static).update(
            f"Ringing for {hours:02d}:{minutes:02d}:{secs:02d}"
        )

    def action_ring_snooze(self) -> None:
        self.dismiss("snooze")

    def action_ring_dismiss(self) -> None:
        self.dismiss("dismiss")
