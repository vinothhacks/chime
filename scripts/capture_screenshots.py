#!/usr/bin/env python3
"""Capture TUI screenshots (SVG) for the README. Uses a fake clock and temp store."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from chime.application import Application
from chime.clock import FakeClock
from chime.locking import ProcessLock
from chime.models import ActiveRing
from chime.sound import NullAudioPlayer
from chime.store import Store
from chime.tui.app import ChimeApp
from chime.tui.screens.edit_alarm import EditAlarmScreen
from chime.tui.screens.help import HelpScreen
from chime.tui.screens.ringing import RingingScreen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"


async def _capture() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data_dir = ROOT / "demo-data"
    data_dir.mkdir(exist_ok=True)
    clock = FakeClock(datetime(2026, 9, 15, 7, 28, 41, tzinfo=ZoneInfo("Asia/Kolkata")))
    store = Store(data_dir, ProcessLock(data_dir / "chime.lock"))
    if store.primary.exists():
        store.primary.unlink()
    if store.backup.exists():
        store.backup.unlink()
    app_layer = Application(store, clock)
    app_layer.create_alarm("07:30", days_raw="weekdays", label="Gym", timezone="Asia/Kolkata")
    app_layer.create_alarm("08:15", days_raw="weekends", label="Weekend", timezone="Asia/Kolkata")
    weekend = [item for item in app_layer.list_alarms() if item.label == "Weekend"][0]
    app_layer.set_alarm_enabled(weekend.id, False)
    app_layer.create_alarm(
        "22:00", days_raw="weekdays,sat,sun", label="Wind down", timezone="Asia/Kolkata"
    )

    tui = ChimeApp(app_layer, audio=NullAudioPlayer(), auto_dismiss_on_exit=False)
    async with tui.run_test(size=(100, 28)) as pilot:
        await pilot.pause()
        (OUT / "main.svg").write_text(tui.export_screenshot(), encoding="utf-8")
        await tui.push_screen(HelpScreen())
        await pilot.pause()
        (OUT / "help.svg").write_text(tui.export_screenshot(), encoding="utf-8")
        await tui.pop_screen()
        await tui.push_screen(EditAlarmScreen())
        await pilot.pause()
        (OUT / "edit.svg").write_text(tui.export_screenshot(), encoding="utf-8")
        await tui.pop_screen()
        alarm = app_layer.list_alarms()[0]
        ring = ActiveRing(
            alarm_id=alarm.id,
            occurrence_key=f"{alarm.id}:2026-09-15:07:30:0",
            started_at_utc=clock.now_utc(),
            snoozes_used=0,
        )
        await tui.push_screen(
            RingingScreen(ring, alarm, True, clock.now_utc(), audio=NullAudioPlayer())
        )
        await pilot.pause()
        (OUT / "ringing.svg").write_text(tui.export_screenshot(), encoding="utf-8")


def main() -> None:
    asyncio.run(_capture())
    print(f"wrote screenshots to {OUT}")


if __name__ == "__main__":
    main()
