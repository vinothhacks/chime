from __future__ import annotations

import json
from pathlib import Path

import pytest

from chime.errors import CorruptStateError, LockError, MigrationError
from chime.locking import ProcessLock
from chime.models import SCHEMA_VERSION, Alarm, AppState, ScheduleKind, Settings
from chime.store import Store, parse_state, serialize_state


def test_atomic_save_and_roundtrip(tmp_path: Path) -> None:
    store = Store(tmp_path)
    state = AppState(
        settings=Settings(default_timezone="Asia/Kolkata"),
        alarms=(
            Alarm(
                id="abcd1234",
                local_time="07:30",
                timezone="Asia/Kolkata",
                kind=ScheduleKind.ONCE,
                days=frozenset(),
                label="Gym",
            ),
        ),
    )
    store.save(state)
    loaded = store.load()
    assert loaded.alarms[0].label == "Gym"
    assert loaded.schema_version == SCHEMA_VERSION
    assert store.backup.exists()


def test_deterministic_json(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.save(AppState())
    first = store.primary.read_text(encoding="utf-8")
    store.save(store.load())
    second = store.primary.read_text(encoding="utf-8")
    assert first == second
    json.loads(first)


def test_corrupt_primary_uses_backup(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.save(
        AppState(
            alarms=(
                Alarm(
                    id="abcd1234",
                    local_time="08:00",
                    timezone="UTC",
                    kind=ScheduleKind.ONCE,
                    days=frozenset(),
                    label="Keep",
                ),
            )
        )
    )
    store.primary.write_text("{not json", encoding="utf-8")
    loaded = store.load()
    assert store.recovered_from_backup is True
    assert loaded.alarms[0].label == "Keep"


def test_both_corrupt_refuses_to_wipe(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.primary.write_text("{bad", encoding="utf-8")
    store.backup.write_text("{bad", encoding="utf-8")
    with pytest.raises(CorruptStateError):
        store.load()
    assert store.primary.read_text(encoding="utf-8") == "{bad"


def test_unknown_schema_version(tmp_path: Path) -> None:
    store = Store(tmp_path)
    store.primary.write_text(
        json.dumps({"schema_version": 99, "settings": {}, "alarms": [], "runtime": {}}),
        encoding="utf-8",
    )
    with pytest.raises((MigrationError, CorruptStateError)):
        store.load()


def test_schema_v1_migrates() -> None:
    state = parse_state(
        {
            "schema_version": 1,
            "settings": {"default_timezone": "UTC"},
            "alarms": [
                {
                    "id": "abcd1234",
                    "local_time": "07:30",
                    "timezone": "UTC",
                    "days": [],
                    "label": "Old",
                }
            ],
        }
    )
    assert state.schema_version == 2
    assert state.alarms[0].kind is ScheduleKind.ONCE
    dumped = serialize_state(state)
    assert dumped["schema_version"] == 2
    assert "runtime" in dumped


def test_lock_blocks_second_writer(tmp_path: Path) -> None:
    path = tmp_path / "chime.lock"
    first = ProcessLock(path)
    second = ProcessLock(path)
    assert first.acquire(blocking=False) is True
    with pytest.raises(LockError):
        second.acquire(blocking=False)
    first.release()
    assert second.acquire(blocking=False) is True
    second.release()
