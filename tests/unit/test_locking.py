from __future__ import annotations

import sys
from pathlib import Path

from chime.locking import ProcessLock


def test_lock_held_property(tmp_path: Path) -> None:
    lock = ProcessLock(tmp_path / "chime.lock")
    assert lock.held is False
    lock.acquire(blocking=False)
    assert lock.held is True
    lock.release()
    assert lock.held is False


def test_lock_context_manager(tmp_path: Path) -> None:
    path = tmp_path / "chime.lock"
    with ProcessLock(path) as lock:
        assert lock.held is True
        other = ProcessLock(path)
        acquired = True
        try:
            other.acquire(blocking=False)
        except Exception:
            acquired = False
        if acquired:
            other.release()
        if sys.platform != "win32":
            assert acquired is False
