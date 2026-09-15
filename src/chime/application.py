"""Shared use cases for CLI and TUI. Neither layer writes JSON directly."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from chime.clock import Clock, SystemClock, ensure_aware_utc
from chime.errors import NotFoundError, ValidationError
from chime.models import (
    MAX_ALARMS,
    MAX_LABEL_LEN,
    RING_TIMEOUT_MINUTES,
    ActiveRing,
    Alarm,
    AppState,
    ClaimedOccurrence,
    Decision,
    Occurrence,
    ScheduleKind,
    Snooze,
    Weekday,
)
from chime.scheduler import (
    evaluate_occurrence,
    evaluate_snoozes,
    next_occurrence,
    occurrences_between,
)
from chime.store import Store, prune_claims
from chime.time_utils import parse_days, parse_local_time, validate_timezone


@dataclass(frozen=True, slots=True)
class TickResult:
    state: AppState
    ring: ActiveRing | None
    snooze_ring: bool
    missed_keys: tuple[str, ...]
    next_occurrence: Occurrence | None
    recovered_from_backup: bool
    timeout: bool


class Application:
    def __init__(self, store: Store, clock: Clock | None = None) -> None:
        self.store = store
        self.clock = clock or SystemClock()

    def create_alarm(
        self,
        time_raw: str,
        *,
        once: bool = False,
        days_raw: str | None = None,
        label: str = "",
        timezone: str | None = None,
        snooze_minutes: int = 9,
        max_snoozes: int = 3,
        sound: str = "default",
        enabled: bool = True,
    ) -> Alarm:
        alarm = self._build_alarm(
            ident=None,
            time_raw=time_raw,
            once=once,
            days_raw=days_raw,
            label=label,
            timezone=timezone,
            snooze_minutes=snooze_minutes,
            max_snoozes=max_snoozes,
            sound=sound,
            enabled=enabled,
        )

        def apply(state: AppState) -> AppState:
            if len(state.alarms) >= MAX_ALARMS:
                raise ValidationError(f"maximum of {MAX_ALARMS} alarms reached")
            existing = {item.id for item in state.alarms}
            ident = _new_id(existing)
            created = replace(alarm, id=ident)
            return replace(state, alarms=(*state.alarms, created))

        new_state = self.store.mutate(apply)
        return new_state.alarms[-1]

    def update_alarm(
        self,
        ident: str,
        *,
        time_raw: str | None = None,
        once: bool | None = None,
        days_raw: str | None = None,
        label: str | None = None,
        timezone: str | None = None,
        snooze_minutes: int | None = None,
        max_snoozes: int | None = None,
        sound: str | None = None,
        enabled: bool | None = None,
    ) -> Alarm:
        def apply(state: AppState) -> AppState:
            current = _require(state, ident)
            kind_once = once if once is not None else current.kind is ScheduleKind.ONCE
            days = days_raw
            if once is True:
                days = None
            rebuilt = self._build_alarm(
                ident=current.id,
                time_raw=time_raw if time_raw is not None else current.local_time,
                once=kind_once,
                days_raw=days
                if days is not None
                else (
                    None
                    if kind_once
                    else ",".join(day.name.lower() for day in sorted(current.days, key=int))
                ),
                label=current.label if label is None else label,
                timezone=current.timezone if timezone is None else timezone,
                snooze_minutes=current.snooze_minutes if snooze_minutes is None else snooze_minutes,
                max_snoozes=current.max_snoozes if max_snoozes is None else max_snoozes,
                sound=current.sound if sound is None else sound,
                enabled=current.enabled if enabled is None else enabled,
            )
            alarms = tuple(rebuilt if item.id == ident else item for item in state.alarms)
            return replace(state, alarms=alarms)

        new_state = self.store.mutate(apply)
        return _require(new_state, ident)

    def delete_alarm(self, ident: str) -> None:
        def apply(state: AppState) -> AppState:
            _require(state, ident)
            alarms = tuple(item for item in state.alarms if item.id != ident)
            runtime = state.runtime
            if runtime.active_ring and runtime.active_ring.alarm_id == ident:
                runtime = replace(runtime, active_ring=None)
            snoozes = tuple(item for item in runtime.snoozes if item.alarm_id != ident)
            runtime = replace(runtime, snoozes=snoozes)
            return replace(state, alarms=alarms, runtime=runtime)

        self.store.mutate(apply)

    def set_alarm_enabled(self, ident: str, enabled: bool) -> Alarm:
        def apply(state: AppState) -> AppState:
            _require(state, ident)
            alarms = tuple(
                replace(item, enabled=enabled) if item.id == ident else item
                for item in state.alarms
            )
            return replace(state, alarms=alarms)

        return _require(self.store.mutate(apply), ident)

    def list_alarms(self) -> tuple[Alarm, ...]:
        return self.store.load().alarms

    def load_state(self) -> AppState:
        return self.store.load()

    def set_format_24h(self, enabled: bool) -> AppState:
        def apply(state: AppState) -> AppState:
            return replace(state, settings=replace(state.settings, format_24h=enabled))

        return self.store.mutate(apply)

    def process_clock_tick(self) -> TickResult:
        missed: list[str] = []
        ring: ActiveRing | None = None
        snooze_ring = False
        nxt: Occurrence | None = None
        timeout = False

        def apply(state: AppState) -> AppState:
            nonlocal missed, ring, snooze_ring, nxt, timeout
            now = ensure_aware_utc(self.clock.now_utc())
            grace = timedelta(minutes=state.settings.grace_minutes)
            protect: set[str] = set()
            if state.runtime.active_ring is not None:
                protect.add(state.runtime.active_ring.occurrence_key)
            claims = list(prune_claims(state.runtime.claimed_occurrences, now, protect=protect))
            claimed_keys = {item.key for item in claims}
            snoozes = list(state.runtime.snoozes)
            alarms = list(state.alarms)
            active = state.runtime.active_ring

            if active is not None:
                if now - active.started_at_utc >= timedelta(minutes=RING_TIMEOUT_MINUTES):
                    timeout = True
                    missed.append(active.occurrence_key)
                    alarms = _disable_once(alarms, active.alarm_id)
                    active = None
                else:
                    ring = active

            if active is None:
                due = evaluate_snoozes(snoozes, now)
                if due:
                    first = due[0]
                    snoozes = [item for item in snoozes if item.id != first.id]
                    active = ActiveRing(
                        alarm_id=first.alarm_id,
                        occurrence_key=f"snooze:{first.id}",
                        started_at_utc=now,
                        snoozes_used=first.count,
                    )
                    ring = active
                    snooze_ring = True

            if active is None:
                window_start = now - timedelta(days=8)
                ring_candidates: list[tuple[datetime, Occurrence, Alarm]] = []
                for alarm in alarms:
                    if not alarm.enabled:
                        continue
                    occs = occurrences_between(alarm, window_start, now)
                    if alarm.kind is ScheduleKind.ONCE:
                        occs = occs[-1:] if occs else []
                    for occ in occs:
                        decision = evaluate_occurrence(occ, now, grace, claimed_keys)
                        if decision is Decision.MISSED:
                            claims.append(ClaimedOccurrence(key=occ.key, claimed_at_utc=now))
                            claimed_keys.add(occ.key)
                            missed.append(occ.key)
                            if alarm.kind is ScheduleKind.ONCE:
                                alarms = _disable_once(alarms, alarm.id)
                        elif decision is Decision.RING:
                            ring_candidates.append((occ.scheduled_utc, occ, alarm))
                if ring_candidates:
                    ring_candidates.sort(key=lambda item: item[0])
                    _, occ, alarm = ring_candidates[0]
                    claims.append(ClaimedOccurrence(key=occ.key, claimed_at_utc=now))
                    claimed_keys.add(occ.key)
                    active = ActiveRing(
                        alarm_id=alarm.id,
                        occurrence_key=occ.key,
                        started_at_utc=now,
                        snoozes_used=0,
                    )
                    ring = active

            nxt = _soonest_future(alarms, now, claimed_keys)
            runtime = replace(
                state.runtime,
                claimed_occurrences=tuple(claims),
                snoozes=tuple(snoozes),
                active_ring=active,
            )
            return replace(state, alarms=tuple(alarms), runtime=runtime)

        new_state = self.store.mutate(apply)
        return TickResult(
            state=new_state,
            ring=ring,
            snooze_ring=snooze_ring,
            missed_keys=tuple(missed),
            next_occurrence=nxt,
            recovered_from_backup=self.store.recovered_from_backup,
            timeout=timeout,
        )

    def snooze_active_ring(self) -> Snooze:
        created: Snooze | None = None

        def apply(state: AppState) -> AppState:
            nonlocal created
            active = state.runtime.active_ring
            if active is None:
                raise ValidationError("no alarm is ringing")
            alarm = _require(state, active.alarm_id)
            if active.snoozes_used >= alarm.max_snoozes:
                raise ValidationError("maximum snoozes reached")
            now = ensure_aware_utc(self.clock.now_utc())
            created = Snooze(
                id=uuid.uuid4().hex[:12],
                alarm_id=alarm.id,
                until_utc=now + timedelta(minutes=alarm.snooze_minutes),
                count=active.snoozes_used + 1,
            )
            runtime = replace(
                state.runtime,
                active_ring=None,
                snoozes=(*state.runtime.snoozes, created),
            )
            return replace(state, runtime=runtime)

        self.store.mutate(apply)
        assert created is not None
        return created

    def dismiss_active_ring(self) -> AppState:
        def apply(state: AppState) -> AppState:
            active = state.runtime.active_ring
            if active is None:
                raise ValidationError("no alarm is ringing")
            alarms = _disable_once(list(state.alarms), active.alarm_id)
            runtime = replace(state.runtime, active_ring=None)
            return replace(state, alarms=tuple(alarms), runtime=runtime)

        return self.store.mutate(apply)

    def _build_alarm(
        self,
        *,
        ident: str | None,
        time_raw: str,
        once: bool,
        days_raw: str | None,
        label: str,
        timezone: str | None,
        snooze_minutes: int,
        max_snoozes: int,
        sound: str,
        enabled: bool,
    ) -> Alarm:
        local_time = parse_local_time(time_raw)
        if len(label) > MAX_LABEL_LEN:
            raise ValidationError(f"label must be at most {MAX_LABEL_LEN} characters")
        if not 1 <= snooze_minutes <= 60:
            raise ValidationError("snooze minutes must be between 1 and 60")
        if not 0 <= max_snoozes <= 9:
            raise ValidationError("max snoozes must be between 0 and 9")
        if sound != "default":
            raise ValidationError("v1 only supports the default bundled sound")
        tz = timezone or self.store.load().settings.default_timezone
        if not tz:
            from chime.config import default_timezone as detect_tz

            tz = detect_tz()
        validate_timezone(tz)
        if once:
            if days_raw:
                raise ValidationError("once alarms must not include weekdays")
            kind = ScheduleKind.ONCE
            days: frozenset[Weekday] = frozenset()
        else:
            if not days_raw:
                raise ValidationError("weekly alarms require --days or --once")
            kind = ScheduleKind.WEEKLY
            days = parse_days(days_raw)
        return Alarm(
            id=ident or "pending",
            local_time=local_time,
            timezone=tz,
            kind=kind,
            days=days,
            label=label,
            enabled=enabled,
            snooze_minutes=snooze_minutes,
            max_snoozes=max_snoozes,
            sound=sound,
        )


def _new_id(existing: set[str]) -> str:
    for _ in range(64):
        ident = uuid.uuid4().hex[:8]
        if ident not in existing:
            return ident
    raise ValidationError("could not allocate an alarm id")


def _require(state: AppState, ident: str) -> Alarm:
    for item in state.alarms:
        if item.id == ident:
            return item
    raise NotFoundError(f"alarm not found: {ident}")


def _disable_once(alarms: list[Alarm], ident: str) -> list[Alarm]:
    result: list[Alarm] = []
    for item in alarms:
        if item.id == ident and item.kind is ScheduleKind.ONCE:
            result.append(replace(item, enabled=False))
        else:
            result.append(item)
    return result


def _soonest_future(
    alarms: list[Alarm],
    now: datetime,
    claimed_keys: set[str],
) -> Occurrence | None:
    soonest: Occurrence | None = None
    for alarm in alarms:
        if not alarm.enabled:
            continue
        occ = next_occurrence(alarm, now)
        if occ is None or occ.key in claimed_keys:
            continue
        if soonest is None or occ.scheduled_utc < soonest.scheduled_utc:
            soonest = occ
    return soonest
