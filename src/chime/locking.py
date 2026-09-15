"""OS advisory lock. Existence of the lock file is not authoritative."""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType
from typing import IO

from chime.errors import LockError

# msvcrt allows the same process to lock the same byte range twice. Track
# held paths so a second ProcessLock in this process still fails, matching
# Unix flock and the CLI-vs-TUI rule.
_HELD_PATHS: set[str] = set()


class ProcessLock:
    """Exclusive lock on `chime.lock` via flock (Unix) or msvcrt (Windows)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[bytes] | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self, *, blocking: bool = False) -> bool:
        if self.held:
            return True
        key = str(self.path.resolve())
        if key in _HELD_PATHS:
            raise LockError("chime is already running")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115
        try:
            handle.seek(0)
            if handle.read(1) == b"":
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if sys.platform == "win32":
                self._acquire_windows(handle, blocking=blocking)
            else:
                self._acquire_unix(handle, blocking=blocking)
        except LockError:
            handle.close()
            raise
        except OSError as exc:
            handle.close()
            if not blocking:
                return False
            raise LockError("chime is already running") from exc
        _HELD_PATHS.add(key)
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        _HELD_PATHS.discard(str(self.path.resolve()))
        if handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        finally:
            handle.close()

    def __enter__(self) -> ProcessLock:
        if not self.acquire(blocking=False):
            raise LockError("chime is already running")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()

    def _acquire_windows(self, handle: IO[bytes], *, blocking: bool) -> None:
        import msvcrt

        mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
        try:
            msvcrt.locking(handle.fileno(), mode, 1)
        except OSError as exc:
            raise LockError("chime is already running") from exc

    def _acquire_unix(self, handle: IO[bytes], *, blocking: bool) -> None:
        import fcntl

        flags = fcntl.LOCK_EX  # type: ignore[attr-defined]
        if not blocking:
            flags |= fcntl.LOCK_NB  # type: ignore[attr-defined]
        try:
            fcntl.flock(handle.fileno(), flags)  # type: ignore[attr-defined]
        except BlockingIOError as exc:
            raise LockError("chime is already running") from exc
