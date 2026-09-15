from __future__ import annotations

from pathlib import Path

import pytest

from chime.application import Application
from chime.clock import FakeClock
from chime.locking import ProcessLock
from chime.sound import NullAudioPlayer
from chime.store import Store
from chime.tui.app import ChimeApp


@pytest.mark.asyncio
async def test_tui_add_and_quit(data_dir: Path, clock: FakeClock) -> None:
    store = Store(data_dir, ProcessLock(data_dir / "chime.lock"))
    application = Application(store, clock)
    application.create_alarm("07:30", once=True, label="Gym", timezone="Asia/Kolkata")
    app = ChimeApp(application, audio=NullAudioPlayer(), auto_dismiss_on_exit=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.press("q")
    assert application.list_alarms()[0].label == "Gym"


@pytest.mark.asyncio
async def test_tui_toggle(data_dir: Path, clock: FakeClock) -> None:
    store = Store(data_dir, ProcessLock(data_dir / "chime.lock"))
    application = Application(store, clock)
    application.create_alarm("07:30", once=True, label="Gym")
    app = ChimeApp(application, audio=NullAudioPlayer(), auto_dismiss_on_exit=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("space")
        await pilot.pause()
    assert application.list_alarms()[0].enabled is False


@pytest.mark.asyncio
async def test_tui_shows_indian_time_not_tokyo(data_dir: Path, clock: FakeClock) -> None:
    store = Store(data_dir, ProcessLock(data_dir / "chime.lock"))
    application = Application(store, clock)
    app = ChimeApp(application, audio=NullAudioPlayer(), auto_dismiss_on_exit=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        subtitle = app.sub_title or ""
        assert "Tokyo" not in subtitle
        assert "IST" in subtitle
