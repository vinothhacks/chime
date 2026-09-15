"""Versioned JSON store with atomic replace, backup recovery, and locking."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from chime.errors import CorruptStateError, MigrationError, StorageError, ValidationError
from chime.locking import ProcessLock
from chime.models import (
    CLAIM_RETENTION_DAYS,
    MAX_ALARMS,
    MAX_JSON_BYTES,
    MAX_LABEL_LEN,
    SCHEMA_VERSION,
    ActiveRing,
    Alarm,
    AppState,
    ClaimedOccurrence,
    RuntimeState,
    ScheduleKind,
    Settings,
    Snooze,
    Weekday,
)
from chime.time_utils import parse_local_time, validate_timezone


def utc_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValidationError("naive datetime cannot be persisted")
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def iso_to_utc(raw: str) -> datetime:
    text = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CorruptStateError(f"invalid timestamp: {raw}") from exc
    if parsed.tzinfo is None:
        raise CorruptStateError(f"naive timestamp: {raw}")
    return parsed.astimezone(UTC)


class Store:
    def __init__(self, data_dir: Path, lock: ProcessLock | None = None) -> None:
        self.data_dir = data_dir
        self.primary = data_dir / "alarms.json"
        self.backup = data_dir / "alarms.json.bak"
        self.lock = lock or ProcessLock(data_dir / "chime.lock")
        self.recovered_from_backup = False

    def ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(self.data_dir, 0o700)
            except OSError:
                pass

    def load(self, *, allow_reset: bool = False) -> AppState:
        self.ensure_dir()
        self.recovered_from_backup = False
        if not self.primary.exists() and not self.backup.exists():
            from chime.config import default_timezone
            from chime.models import Settings

            return AppState(settings=Settings(default_timezone=default_timezone()))
        primary_error: Exception | None = None
        if self.primary.exists():
            try:
                return self._load_path(self.primary)
            except (
                CorruptStateError,
                MigrationError,
                ValidationError,
                json.JSONDecodeError,
            ) as exc:
                primary_error = exc
        if self.backup.exists():
            try:
                state = self._load_path(self.backup)
                self.recovered_from_backup = True
                return state
            except (CorruptStateError, MigrationError, ValidationError, json.JSONDecodeError):
                pass
        if allow_reset:
            return AppState()
        if primary_error is not None:
            raise CorruptStateError(
                "alarms.json is unreadable and backup is unusable; refusing to destroy data"
            ) from primary_error
        raise CorruptStateError("alarm store is unreadable; refusing to destroy data")

    def save(self, state: AppState) -> None:
        self.ensure_dir()
        payload = serialize_state(state)
        encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        data = encoded.encode("utf-8")
        if len(data) > MAX_JSON_BYTES:
            raise StorageError("state exceeds 1 MiB limit")
        tmp = self.data_dir / f".alarms.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.primary)
            if os.name != "nt":
                try:
                    os.chmod(self.primary, 0o600)
                except OSError:
                    pass
            self._refresh_backup(data)
        except OSError as exc:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise StorageError(f"failed to write alarm store: {exc}") from exc

    def mutate(self, fn: Callable[[AppState], AppState], *, allow_reset: bool = False) -> AppState:
        acquired_here = False
        if not self.lock.held:
            if not self.lock.acquire(blocking=False):
                from chime.errors import LockError

                raise LockError("chime is already running")
            acquired_here = True
        try:
            state = self.load(allow_reset=allow_reset)
            new_state = fn(state)
            self.save(new_state)
            return new_state
        finally:
            if acquired_here:
                self.lock.release()

    def _load_path(self, path: Path) -> AppState:
        size = path.stat().st_size
        if size > MAX_JSON_BYTES:
            raise CorruptStateError("alarm store is larger than 1 MiB")
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CorruptStateError("alarm store is not valid UTF-8") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CorruptStateError("alarm store is not valid JSON") from exc
        if not isinstance(data, dict):
            raise CorruptStateError("alarm store root must be an object")
        return parse_state(data)

    def _refresh_backup(self, data: bytes) -> None:
        tmp = self.data_dir / f".alarms.bak.{uuid.uuid4().hex}.tmp"
        try:
            with open(tmp, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.backup)
        except OSError:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass


def serialize_state(state: AppState) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "settings": {
            "format_24h": state.settings.format_24h,
            "theme": state.settings.theme,
            "grace_minutes": state.settings.grace_minutes,
            "default_timezone": state.settings.default_timezone,
        },
        "alarms": [serialize_alarm(alarm) for alarm in state.alarms],
        "runtime": {
            "claimed_occurrences": [
                {"key": item.key, "claimed_at_utc": utc_to_iso(item.claimed_at_utc)}
                for item in state.runtime.claimed_occurrences
            ],
            "snoozes": [serialize_snooze(item) for item in state.runtime.snoozes],
            "active_ring": serialize_ring(state.runtime.active_ring),
        },
    }
    for key, value in state.extras.items():
        if key not in payload:
            payload[key] = value
    return payload


def serialize_alarm(alarm: Alarm) -> dict[str, Any]:
    return {
        "id": alarm.id,
        "local_time": alarm.local_time,
        "timezone": alarm.timezone,
        "kind": str(alarm.kind),
        "days": sorted(int(day) for day in alarm.days),
        "label": alarm.label,
        "enabled": alarm.enabled,
        "snooze_minutes": alarm.snooze_minutes,
        "max_snoozes": alarm.max_snoozes,
        "sound": alarm.sound,
    }


def serialize_snooze(item: Snooze) -> dict[str, Any]:
    return {
        "id": item.id,
        "alarm_id": item.alarm_id,
        "until_utc": utc_to_iso(item.until_utc),
        "count": item.count,
    }


def serialize_ring(ring: ActiveRing | None) -> dict[str, Any] | None:
    if ring is None:
        return None
    return {
        "alarm_id": ring.alarm_id,
        "occurrence_key": ring.occurrence_key,
        "started_at_utc": utc_to_iso(ring.started_at_utc),
        "snoozes_used": ring.snoozes_used,
    }


def parse_state(data: dict[str, Any]) -> AppState:
    version = data.get("schema_version", 1)
    if not isinstance(version, int):
        raise CorruptStateError("schema_version must be an integer")
    if version > SCHEMA_VERSION:
        raise MigrationError(f"unsupported schema_version {version}")
    if version < 1:
        raise MigrationError(f"unsupported schema_version {version}")
    migrated = migrate(data, version)
    known = {"schema_version", "settings", "alarms", "runtime"}
    extras = {key: value for key, value in migrated.items() if key not in known}
    settings = parse_settings(migrated.get("settings") or {})
    alarms_raw = migrated.get("alarms")
    if not isinstance(alarms_raw, list):
        raise CorruptStateError("alarms must be a list")
    if len(alarms_raw) > MAX_ALARMS:
        raise CorruptStateError(f"too many alarms (max {MAX_ALARMS})")
    alarms = tuple(parse_alarm(item) for item in alarms_raw)
    runtime = parse_runtime(migrated.get("runtime") or {})
    return AppState(
        schema_version=SCHEMA_VERSION,
        settings=settings,
        alarms=alarms,
        runtime=runtime,
        extras=extras,
    )


def migrate(data: dict[str, Any], version: int) -> dict[str, Any]:
    current = dict(data)
    if version == SCHEMA_VERSION:
        return current
    if version == 1:
        current.setdefault(
            "runtime", {"claimed_occurrences": [], "snoozes": [], "active_ring": None}
        )
        current["schema_version"] = 2
        alarms = current.get("alarms")
        if isinstance(alarms, list):
            for item in alarms:
                if isinstance(item, dict) and "kind" not in item:
                    days = item.get("days") or []
                    item["kind"] = "weekly" if days else "once"
        return current
    raise MigrationError(f"no migration from schema_version {version}")


def parse_settings(raw: Any) -> Settings:
    if not isinstance(raw, dict):
        raise CorruptStateError("settings must be an object")
    grace = raw.get("grace_minutes", 5)
    if not isinstance(grace, int) or grace < 0 or grace > 180:
        raise CorruptStateError("grace_minutes out of range")
    tz = raw.get("default_timezone", "UTC")
    if not isinstance(tz, str):
        raise CorruptStateError("default_timezone must be a string")
    try:
        validate_timezone(tz)
    except ValidationError as exc:
        raise CorruptStateError(str(exc)) from exc
    theme = raw.get("theme", "tokyo-night")
    if not isinstance(theme, str):
        raise CorruptStateError("theme must be a string")
    fmt = raw.get("format_24h", True)
    if not isinstance(fmt, bool):
        raise CorruptStateError("format_24h must be a boolean")
    return Settings(
        format_24h=fmt,
        theme=theme,
        grace_minutes=grace,
        default_timezone=tz,
    )


def parse_alarm(raw: Any) -> Alarm:
    if not isinstance(raw, dict):
        raise CorruptStateError("alarm must be an object")
    ident = raw.get("id")
    if not isinstance(ident, str) or not ident:
        raise CorruptStateError("alarm id is required")
    try:
        local_time = parse_local_time(str(raw.get("local_time", "")))
    except ValidationError as exc:
        raise CorruptStateError(str(exc)) from exc
    tz = raw.get("timezone")
    if not isinstance(tz, str):
        raise CorruptStateError("alarm timezone is required")
    try:
        validate_timezone(tz)
    except ValidationError as exc:
        raise CorruptStateError(str(exc)) from exc
    kind_raw = raw.get("kind", "once")
    try:
        kind = ScheduleKind(kind_raw)
    except ValueError as exc:
        raise CorruptStateError(f"invalid schedule kind: {kind_raw}") from exc
    days_raw = raw.get("days") or []
    if not isinstance(days_raw, list):
        raise CorruptStateError("days must be a list")
    days: set[Weekday] = set()
    for item in days_raw:
        if not isinstance(item, int) or item not in range(7):
            raise CorruptStateError(f"invalid weekday: {item}")
        days.add(Weekday(item))
    if kind is ScheduleKind.WEEKLY and not days:
        raise CorruptStateError("weekly alarm requires at least one weekday")
    if kind is ScheduleKind.ONCE and days:
        raise CorruptStateError("once alarm must not have weekdays")
    label = raw.get("label", "")
    if not isinstance(label, str) or len(label) > MAX_LABEL_LEN:
        raise CorruptStateError("invalid label")
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise CorruptStateError("enabled must be a boolean")
    snooze = raw.get("snooze_minutes", 9)
    max_snoozes = raw.get("max_snoozes", 3)
    if not isinstance(snooze, int) or not 1 <= snooze <= 60:
        raise CorruptStateError("snooze_minutes out of range")
    if not isinstance(max_snoozes, int) or not 0 <= max_snoozes <= 9:
        raise CorruptStateError("max_snoozes out of range")
    sound = raw.get("sound", "default")
    if not isinstance(sound, str):
        raise CorruptStateError("sound must be a string")
    return Alarm(
        id=ident,
        local_time=local_time,
        timezone=tz,
        kind=kind,
        days=frozenset(days),
        label=label,
        enabled=enabled,
        snooze_minutes=snooze,
        max_snoozes=max_snoozes,
        sound=sound,
    )


def parse_runtime(raw: Any) -> RuntimeState:
    if not isinstance(raw, dict):
        raise CorruptStateError("runtime must be an object")
    claimed_raw = raw.get("claimed_occurrences") or []
    if not isinstance(claimed_raw, list):
        raise CorruptStateError("claimed_occurrences must be a list")
    claimed: list[ClaimedOccurrence] = []
    for item in claimed_raw:
        if not isinstance(item, dict):
            raise CorruptStateError("claimed occurrence must be an object")
        key = item.get("key")
        ts = item.get("claimed_at_utc")
        if not isinstance(key, str) or not isinstance(ts, str):
            raise CorruptStateError("claimed occurrence is missing fields")
        claimed.append(ClaimedOccurrence(key=key, claimed_at_utc=iso_to_utc(ts)))
    snoozes_raw = raw.get("snoozes") or []
    if not isinstance(snoozes_raw, list):
        raise CorruptStateError("snoozes must be a list")
    snoozes = tuple(parse_snooze(item) for item in snoozes_raw)
    ring = parse_ring(raw.get("active_ring"))
    return RuntimeState(
        claimed_occurrences=tuple(claimed),
        snoozes=snoozes,
        active_ring=ring,
    )


def parse_snooze(raw: Any) -> Snooze:
    if not isinstance(raw, dict):
        raise CorruptStateError("snooze must be an object")
    ident = raw.get("id")
    alarm_id = raw.get("alarm_id")
    until = raw.get("until_utc")
    count = raw.get("count", 1)
    if not isinstance(ident, str) or not isinstance(alarm_id, str) or not isinstance(until, str):
        raise CorruptStateError("snooze is missing fields")
    if not isinstance(count, int) or count < 1:
        raise CorruptStateError("invalid snooze count")
    return Snooze(id=ident, alarm_id=alarm_id, until_utc=iso_to_utc(until), count=count)


def parse_ring(raw: Any) -> ActiveRing | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CorruptStateError("active_ring must be an object")
    alarm_id = raw.get("alarm_id")
    key = raw.get("occurrence_key")
    started = raw.get("started_at_utc")
    used = raw.get("snoozes_used", 0)
    if not isinstance(alarm_id, str) or not isinstance(key, str) or not isinstance(started, str):
        raise CorruptStateError("active_ring is missing fields")
    if not isinstance(used, int) or used < 0:
        raise CorruptStateError("invalid snoozes_used")
    return ActiveRing(
        alarm_id=alarm_id,
        occurrence_key=key,
        started_at_utc=iso_to_utc(started),
        snoozes_used=used,
    )


def prune_claims(
    claims: tuple[ClaimedOccurrence, ...],
    now: datetime,
    *,
    protect: set[str],
) -> tuple[ClaimedOccurrence, ...]:
    cutoff = now.astimezone(UTC) - timedelta(days=CLAIM_RETENTION_DAYS)
    kept: list[ClaimedOccurrence] = []
    for item in claims:
        if item.key in protect or item.claimed_at_utc >= cutoff:
            kept.append(item)
    return tuple(kept)
