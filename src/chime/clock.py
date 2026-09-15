"""Injected clocks. Domain code never calls datetime.now()."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


def ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        msg = "naive datetime is not allowed at the application boundary"
        raise ValueError(msg)
    return dt.astimezone(UTC)


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def now_local(self, tz_name: str) -> datetime: ...


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def now_local(self, tz_name: str) -> datetime:
        return datetime.now(ZoneInfo(tz_name))


class FakeClock:
    """Mutable clock for tests. `now` must be timezone-aware."""

    def __init__(self, now: datetime) -> None:
        self._now = ensure_aware_utc(now)

    def now_utc(self) -> datetime:
        return self._now

    def now_local(self, tz_name: str) -> datetime:
        return self._now.astimezone(ZoneInfo(tz_name))

    def set(self, now: datetime) -> None:
        self._now = ensure_aware_utc(now)

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)
