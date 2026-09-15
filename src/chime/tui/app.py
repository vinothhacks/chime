from __future__ import annotations

import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static

from chime.application import Application
from chime.clock import SystemClock
from chime.config import data_dir, default_timezone
from chime.errors import ChimeError, LockError, ValidationError
from chime.locking import ProcessLock
from chime.models import Alarm
from chime.sound import AudioPlayer, DefaultAudioPlayer
from chime.store import Store
from chime.tui.screens.edit_alarm import EditAlarmScreen
from chime.tui.screens.help import HelpScreen
from chime.tui.screens.main import AlarmList, AlarmListItem
from chime.tui.screens.ringing import RingingScreen
from chime.tui.widgets.big_clock import BigClock
from chime.tui.widgets.next_alarm import NextAlarm


class ChimeApp(App[None]):
    CSS_PATH = "styles.tcss"
    TITLE = "CHIME"
    SUB_TITLE = "India · IST"
    BINDINGS = [
        Binding("a", "add_alarm", "Add", show=True),
        Binding("e", "edit_alarm", "Edit", show=True),
        Binding("d", "delete_alarm", "Delete", show=True),
        Binding("space", "toggle_alarm", "Toggle", show=True),
        Binding("t", "test_sound", "Test", show=True),
        Binding("question_mark", "help", "Help", show=True),
        Binding("f2", "toggle_clock", "12/24h", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        application: Application,
        audio: AudioPlayer | None = None,
        *,
        auto_dismiss_on_exit: bool = True,
    ) -> None:
        super().__init__()
        self.application = application
        self.audio = audio if audio is not None else DefaultAudioPlayer()
        self.auto_dismiss_on_exit = auto_dismiss_on_exit
        self._ringing = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="hero"):
            yield BigClock("00:00:00", id="clock")
            yield Static("", id="date-line")
            yield NextAlarm("Next: none", id="next")
        yield AlarmList(id="alarms")
        yield Footer()

    def on_mount(self) -> None:
        self.theme = "textual-dark"
        self._refresh()
        self.set_interval(1.0, self._tick)

    def on_unmount(self) -> None:
        if self.auto_dismiss_on_exit:
            state = self.application.load_state()
            if state.runtime.active_ring is not None:
                try:
                    self.application.dismiss_active_ring()
                except ChimeError:
                    pass

    def _tick(self) -> None:
        if self._ringing:
            self._refresh_clock()
            return
        try:
            result = self.application.process_clock_tick()
        except ChimeError as exc:
            self.notify(str(exc), severity="error")
            return
        if result.recovered_from_backup:
            self.notify("Recovered alarm store from backup", severity="warning")
        if result.timeout:
            self.notify("Alarm timed out and was marked missed")
        if result.ring is not None:
            alarm = next(
                (item for item in result.state.alarms if item.id == result.ring.alarm_id),
                None,
            )
            if alarm is not None:
                self._open_ring(result.ring, alarm)
                return
        self._refresh(result)

    def _refresh(self, result: object | None = None) -> None:
        state = self.application.load_state() if result is None else result.state  # type: ignore[attr-defined]
        nxt = None if result is None else result.next_occurrence  # type: ignore[attr-defined]
        if result is None:
            try:
                tick = self.application.process_clock_tick()
                state = tick.state
                nxt = tick.next_occurrence
                if tick.ring is not None and not self._ringing:
                    alarm = next(
                        (item for item in state.alarms if item.id == tick.ring.alarm_id),
                        None,
                    )
                    if alarm is not None:
                        self._open_ring(tick.ring, alarm)
                        return
            except ChimeError:
                pass
        self._refresh_clock()
        self.query_one(AlarmList).set_alarms(state.alarms, state.settings.format_24h)
        now = self.application.clock.now_utc()
        self.query_one(NextAlarm).show(nxt, state.alarms, now)

    def _refresh_clock(self) -> None:
        from chime.config import INDIA_TZ

        state = self.application.load_state()
        local = self.application.clock.now_local(INDIA_TZ)
        self.sub_title = "India · IST"
        self.query_one(BigClock).update_now(local, state.settings.format_24h)
        self.query_one("#date-line", Static).update(local.strftime("%a %d %b %Y") + " · IST")

    def _open_ring(self, ring: object, alarm: Alarm) -> None:
        from chime.models import ActiveRing

        assert isinstance(ring, ActiveRing)
        if self._ringing:
            return
        self._ringing = True
        format_24h = self.application.load_state().settings.format_24h

        def done(action: str | None) -> None:
            self._ringing = False
            try:
                if action == "snooze":
                    self.application.snooze_active_ring()
                else:
                    if self.application.load_state().runtime.active_ring is not None:
                        self.application.dismiss_active_ring()
            except ValidationError as exc:
                self.notify(str(exc), severity="warning")
            except ChimeError as exc:
                self.notify(str(exc), severity="error")
            self._refresh()

        self.push_screen(
            RingingScreen(
                ring,
                alarm,
                format_24h,
                ring.started_at_utc,
                audio=self.audio,
            ),
            done,
        )

    def _selected_alarm(self) -> Alarm | None:
        listing = self.query_one(AlarmList)
        highlighted = listing.highlighted_child
        if isinstance(highlighted, AlarmListItem):
            return highlighted.alarm
        return None

    def action_add_alarm(self) -> None:
        self.push_screen(EditAlarmScreen(), self._on_edit_result)

    def action_edit_alarm(self) -> None:
        alarm = self._selected_alarm()
        if alarm is None:
            self.notify("Select an alarm first")
            return
        self.push_screen(EditAlarmScreen(alarm), lambda data: self._on_edit_result(data, alarm))

    def _on_edit_result(self, data: dict[str, str] | None, existing: Alarm | None = None) -> None:
        if not data:
            return
        try:
            snooze = int(data["snooze"])
            max_snoozes = int(data["max_snoozes"])
            once = data["once"] == "1"
            tz = data.get("timezone", "").strip() or None
            if existing is None:
                self.application.create_alarm(
                    data["time"],
                    once=once,
                    days_raw=None if once else (data["days"] or None),
                    label=data["label"],
                    timezone=tz,
                    snooze_minutes=snooze,
                    max_snoozes=max_snoozes,
                )
            else:
                self.application.update_alarm(
                    existing.id,
                    time_raw=data["time"],
                    once=once,
                    days_raw=None if once else (data["days"] or None),
                    label=data["label"],
                    timezone=tz,
                    snooze_minutes=snooze,
                    max_snoozes=max_snoozes,
                )
        except (ChimeError, ValueError) as exc:
            self.notify(str(exc), severity="error")
        self._refresh()

    def action_delete_alarm(self) -> None:
        alarm = self._selected_alarm()
        if alarm is None:
            self.notify("Select an alarm first")
            return
        try:
            self.application.delete_alarm(alarm.id)
        except ChimeError as exc:
            self.notify(str(exc), severity="error")
        self._refresh()

    def action_toggle_alarm(self) -> None:
        alarm = self._selected_alarm()
        if alarm is None:
            self.notify("Select an alarm first")
            return
        try:
            self.application.set_alarm_enabled(alarm.id, not alarm.enabled)
        except ChimeError as exc:
            self.notify(str(exc), severity="error")
        self._refresh()

    def action_toggle_clock(self) -> None:
        state = self.application.load_state()
        self.application.set_format_24h(not state.settings.format_24h)
        self._refresh()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    async def action_test_sound(self) -> None:
        try:
            await self.audio.start("default")
            self.set_timer(1.5, self.audio.stop)
            self.notify("Playing bundled beep")
        except Exception as exc:
            self.notify(str(exc), severity="warning")


def run_tui(data_dir_override: Path | None = None, audio: AudioPlayer | None = None) -> None:
    if data_dir_override is not None:
        os.environ["CHIME_DATA_DIR"] = str(data_dir_override)
    path = data_dir()
    lock = ProcessLock(path / "chime.lock")
    if not lock.acquire(blocking=False):
        raise LockError("chime is already running")
    try:
        store = Store(path, lock)
        state = store.load(allow_reset=False)
        if not state.settings.default_timezone:
            from dataclasses import replace

            store.save(
                replace(
                    state, settings=replace(state.settings, default_timezone=default_timezone())
                )
            )
        application = Application(store, SystemClock())
        ChimeApp(application, audio=audio or DefaultAudioPlayer()).run()
    finally:
        lock.release()
