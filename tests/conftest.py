from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from chime.application import Application
from chime.clock import FakeClock
from chime.locking import ProcessLock
from chime.store import Store


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CHIME_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHIME_TIMEZONE", "Asia/Kolkata")
    return tmp_path


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 15, 1, 58, 41, tzinfo=UTC))


@pytest.fixture
def store(data_dir: Path) -> Store:
    return Store(data_dir, ProcessLock(data_dir / "chime.lock"))


@pytest.fixture
def app(store: Store, clock: FakeClock) -> Application:
    return Application(store, clock)
