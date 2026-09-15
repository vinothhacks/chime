"""Best-effort audio. Visual ring is mandatory; speaker output is not."""

from __future__ import annotations

import asyncio
import shutil
import sys
from importlib.resources import files
from pathlib import Path
from typing import Protocol

from chime.errors import AudioUnavailableError


class AudioPlayer(Protocol):
    async def start(self, sound: str = "default") -> None: ...

    async def stop(self) -> None: ...

    def diagnostics(self) -> dict[str, str | bool]: ...


class NullAudioPlayer:
    async def start(self, sound: str = "default") -> None:
        return None

    async def stop(self) -> None:
        return None

    def diagnostics(self) -> dict[str, str | bool]:
        return {"backend": "null", "available": True, "bundled_wav": beep_exists()}


def beep_path() -> Path:
    return Path(str(files("chime.resources").joinpath("beep.wav")))


def beep_exists() -> bool:
    try:
        return beep_path().is_file()
    except (FileNotFoundError, ModuleNotFoundError, OSError):
        return False


def detect_backend() -> str:
    if sys.platform == "win32":
        return "winsound"
    if sys.platform == "darwin":
        return "afplay" if shutil.which("afplay") else "bell"
    for name in ("paplay", "aplay", "ffplay", "mpv"):
        if shutil.which(name):
            return name
    return "bell"


def backend_args(backend: str, wav: str) -> list[str]:
    if backend == "ffplay":
        return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", wav]
    if backend == "mpv":
        return ["mpv", "--no-video", "--really-quiet", wav]
    if backend in {"paplay", "aplay", "afplay"}:
        return [backend, wav]
    raise AudioUnavailableError(f"no subprocess backend named {backend}")


class DefaultAudioPlayer:
    def __init__(self) -> None:
        self._backend = detect_backend()
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._proc: asyncio.subprocess.Process | None = None

    def diagnostics(self) -> dict[str, str | bool]:
        return {
            "backend": self._backend,
            "available": True,
            "bundled_wav": beep_exists(),
        }

    async def start(self, sound: str = "default") -> None:
        if sound != "default":
            raise AudioUnavailableError("v1 only supports the bundled beep")
        await self.stop()
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        await self._kill_proc()
        if sys.platform == "win32":
            try:
                import winsound

                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        task = self._task
        self._task = None
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _loop(self) -> None:
        wav = beep_path()
        if not wav.is_file():
            return
        while not self._stop.is_set():
            await self._play_once(str(wav))
            if self._stop.is_set():
                return
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=1.0)
            except TimeoutError:
                continue

    async def _play_once(self, wav: str) -> None:
        if self._backend == "winsound":
            try:
                import winsound

                winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                sys.stdout.write("\a")
                sys.stdout.flush()
            return
        if self._backend == "bell":
            sys.stdout.write("\a")
            sys.stdout.flush()
            return
        args = backend_args(self._backend, wav)
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await self._proc.wait()
        except (FileNotFoundError, OSError):
            sys.stdout.write("\a")
            sys.stdout.flush()
        finally:
            self._proc = None

    async def _kill_proc(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None or proc.returncode is not None:
            return
        try:
            proc.kill()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
        except TimeoutError:
            pass
