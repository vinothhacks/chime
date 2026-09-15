"""Immutable domain types. No framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any


class Weekday(IntEnum):
    MON = 0
    TUE = 1
    WED = 2
    THU = 3
    FRI = 4
    SAT = 5
    SUN = 6


class ScheduleKind(StrEnum):
    ONCE = "once"
    WEEKLY = "weekly"


class Decision(StrEnum):
    NOT_DUE = "not_due"
    RING = "ring"
    MISSED = "missed"
    ALREADY_CLAIMED = "already_claimed"


@dataclass(frozen=True, slots=True)
class Alarm:
    id: str
    local_time: str
    timezone: str
    kind: ScheduleKind
    days: frozenset[Weekday]
    label: str = ""
    enabled: bool = True
    snooze_minutes: int = 9
    max_snoozes: int = 3
    sound: str = "default"


@dataclass(frozen=True, slots=True)
class Occurrence:
    alarm_id: str
    scheduled_local: datetime
    scheduled_utc: datetime
    fold: int

    @property
    def key(self) -> str:
        local = self.scheduled_local
        return f"{self.alarm_id}:{local.date().isoformat()}:{local.strftime('%H:%M')}:{self.fold}"


@dataclass(frozen=True, slots=True)
class Snooze:
    id: str
    alarm_id: str
    until_utc: datetime
    count: int


@dataclass(frozen=True, slots=True)
class ActiveRing:
    alarm_id: str
    occurrence_key: str
    started_at_utc: datetime
    snoozes_used: int


@dataclass(frozen=True, slots=True)
class ClaimedOccurrence:
    key: str
    claimed_at_utc: datetime


@dataclass(frozen=True, slots=True)
class Settings:
    format_24h: bool = True
    theme: str = "tokyo-night"
    grace_minutes: int = 5
    default_timezone: str = "UTC"


@dataclass(frozen=True, slots=True)
class RuntimeState:
    claimed_occurrences: tuple[ClaimedOccurrence, ...] = ()
    snoozes: tuple[Snooze, ...] = ()
    active_ring: ActiveRing | None = None


@dataclass(frozen=True, slots=True)
class AppState:
    schema_version: int = 2
    settings: Settings = field(default_factory=Settings)
    alarms: tuple[Alarm, ...] = ()
    runtime: RuntimeState = field(default_factory=RuntimeState)
    extras: dict[str, Any] = field(default_factory=dict)


MAX_ALARMS = 1000
MAX_LABEL_LEN = 80
MAX_JSON_BYTES = 1_048_576
CLAIM_RETENTION_DAYS = 90
RING_TIMEOUT_MINUTES = 10
SCHEMA_VERSION = 2
