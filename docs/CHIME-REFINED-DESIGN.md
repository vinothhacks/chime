# CHIME — Refined Requirements, Design, and Implementation Plan

> Terminal-native alarm clock for Windows, macOS, and Linux.
> Written before any product code. This document records the thinking: what we accepted,
> what we rejected, what research showed, and how v1 will be built.

**Product name:** chime
**GitHub:** https://github.com/vinothhacks/chime (public)
**Python distribution name:** `chime-alarm` (PyPI name `chime` is already taken)
**Import package:** `chime`
**Console script:** `chime`
**License:** MIT
**Python:** 3.11+
**Primary stack:** Textual 8.2.x, Typer 0.27.x, platformdirs, tzdata, stdlib time/audio

---

## 0. Why this document exists

The source architecture document (`chime-plan-final.md`) is strong on invariants and
weak on a few shipping decisions. This file:

1. Refines requirements into an unambiguous contract.
2. Records research that confirmed or adjusted the stack.
3. Locks the design so CLI and TUI cannot drift.
4. Gives an implementation order that puts the hard parts first.
5. Defines done in a way a test suite can prove.

The optimization target is not line count. It is eliminating ambiguous state
transitions: ring twice, lose alarms, corrupt JSON, or behave differently in CLI vs TUI.

---

## 1. Product boundary

### In scope (v1)

- Typer CLI and Textual TUI in the same process model.
- JSON file persistence under the platform user-data directory.
- One-shot and weekly alarms with local wall-clock times.
- Deterministic occurrence keys, DST policy, grace window, snooze, dismiss.
- Bundled beep via OS audio backends (best-effort).
- `chime doctor` diagnostics.
- Tests, CI on Windows/macOS/Linux, README screenshots.

### Out of scope (do not mix into v1)

- Web UI, React, browser, Textual Web.
- Any database (SQL, SQLite, NoSQL).
- Background daemon or OS scheduler integration.
- Desktop notifications.
- Custom user sound files or shell-configured players.
- Timers, stopwatch, Pomodoro, world-clock dashboard.
- Cloud sync, network access, multiple concurrent TUI writers.

### Hard product truth

**The app must be running to ring.** That is a v1 product limitation, not a bug.
The README must say it in the first screen of documentation.

---

## 2. Research notes

### 2.1 Libraries

| Library | Pin | Evidence |
|---|---|---|
| Textual | `~=8.2.8` | PyPI RSS lists 8.2.8; GitHub releases include 8.2.7 (2026-05-19) and 8.2.8. |
| Typer | `~=0.27.2` | 0.27 line is current (0.27.1/0.27.2). If 0.27.2 is missing at install, take newest 0.27.x. |
| platformdirs | latest compatible | Standard user-data paths; domain must not import it. |
| tzdata | required | Windows and some Linux images have no IANA database. |
| pytest / pytest-asyncio / ruff / mypy / textual-dev / build | dev | Quality gates. |

Textual can serve apps in a browser. **We will not enable that.** User constraint:
CLI/TUI only, no web UI.

### 2.2 PyPI name collision

The existing PyPI project `chime` plays notification sounds. Shipping our wheel as
`chime` would clobber it. Decision:

- GitHub repository: `chime`
- Dist name: `chime-alarm`
- Import: `chime`
- Script: `chime`

Local `uv run chime` is unaffected. A later PyPI publish uses `chime-alarm`.

### 2.3 Time and DST

Python `zoneinfo` plus `fold` is the correct API. Naive `datetime.replace(tzinfo=...)`
is forbidden at the application boundary.

Verified 2026 US DST (America/New_York):

- Spring forward: 2026-03-08 02:00 → 03:00. Local 02:30 **does not exist**. Skip.
- Fall back: 2026-11-01 02:00 → 01:00. Local 01:30 happens twice. Fire **once** at `fold=0`.

Asia/Kolkata has no DST. It is a valid default timezone at alarm creation on this machine.

### 2.4 Locking on Windows

Advisory locks must not trust “file exists”.

- Unix: `fcntl.flock(LOCK_EX | LOCK_NB)` on an open `chime.lock` fd.
- Windows: `msvcrt.locking(LK_NBLCK)` on an open `chime.lock` fd.
- Keep the fd open for the TUI lifetime. Close/unlock on exit.
- Stale lock files after crash are harmless because the OS releases the descriptor.

### 2.5 Audio

V1 bundled WAV only, loaded via `importlib.resources`.

- Windows: `winsound.PlaySound` (no subprocess).
- macOS: `afplay` via `asyncio.create_subprocess_exec`.
- Linux: `paplay` → `aplay` → `ffplay` → `mpv`, then terminal bell.
- Never `shell=True`. Never interpolate user strings into commands.

Audio is outside the durability boundary. The durable event is the persisted claim.

---

## 3. Requirements contract

### 3.1 Alarm types

Exactly two:

1. **Once** (`ScheduleKind.ONCE`): no weekdays. Fires at the next valid occurrence.
   Dismiss disables the alarm.
2. **Weekly** (`ScheduleKind.WEEKLY`): one or more weekdays. Repeats until disabled
   or deleted.

Empty weekday set MUST NOT mean “weekly every day” or “once”. Weekly requires ≥1 day.
Once must have an empty day set.

### 3.2 Time storage

Store:

- `local_time`: `HH:MM` 24-hour
- `timezone`: IANA name, default = zone at creation (`CHIME_TIMEZONE` or platform)
- `days`: frozenset of `Weekday`

Persisted instants (claims, snoozes, ring start) are UTC ISO-8601 with `Z`.

Accepted input times: `07:30`, `7:30`, `730`, `7:30pm`. Normalize to `HH:MM`.
Reject `24:00`, `7:60`, empty, garbage.

### 3.3 DST policy

Owned only by the scheduler:

- Nonexistent local time → skip that day, next valid scheduled day.
- Ambiguous local time → first occurrence (`fold=0`), never twice.
- Occurrence key includes `fold`.

### 3.4 Missed / grace

For a concrete occurrence at `T`:

- `now < T` → NOT_DUE
- `0 <= now - T <= grace` → RING (if unclaimed)
- `now - T > grace` → MISSED (claim it, never ring)
- key already claimed → ALREADY_CLAIMED

Default grace: 5 minutes, global setting.

A clock moving backwards must not re-ring a claimed key.

### 3.5 Snooze

- Default 9 minutes, per-alarm 1..60.
- Max snoozes default 3, per-alarm 0..9.
- Snooze creates a runtime reminder with its own id; it does **not** mutate the
  schedule definition.
- Persist the snooze **before** closing the current ring.
- Fourth snooze when max is 3 is rejected.

### 3.6 Quit while ringing (v1)

Confirm, then **dismiss**: stop audio, persist, exit. Same occurrence must not
ring again on next launch.

### 3.7 CLI surface

```
chime                         # launch TUI
chime add 07:30 --once -l Gym
chime add 07:30 --days weekdays -l Gym
chime add 08:15 --days sat,sun -l Weekend
chime list
chime list --json
chime rm <id>
chime on <id>
chime off <id>
chime test-sound
chime doctor
```

`--json` → JSON only on stdout. Human text on stderr.

Exit codes:

- 0 success
- 1 user/input error
- 2 state/persistence error
- 3 lock/concurrency error
- 4 runtime/backend error

### 3.8 TUI surface

Main: big clock, next-alarm countdown, alarm list, footer bindings.
Edit: time, kind, days, label, timezone, snooze, max snoozes.
Ring: time, label, elapsed, S snooze, D dismiss, 10-minute timeout → missed.
Help: generated from the same binding table as the footer.

Readability: time is dominant; ON/OFF is text not color-only; focused row has a
border; narrow terminals compact rather than overflow; labels ellipsize; no
emoji required for meaning.

### 3.9 Identifiers and limits

- Alarm id: 8-char lowercase hex, uniqueness checked.
- Label: 0..80 characters.
- Alarms: 1..1000.
- JSON payload: reject > 1 MiB.
- Claimed keys: prune older than 90 days, never prune active ring or pending snooze.

### 3.10 Config precedence

`CLI flag > CHIME_* env > persisted settings > platform default`

Env overrides:

- `CHIME_DATA_DIR` — application data root (tests, doctor must show it).
- `CHIME_TIMEZONE` — default IANA zone for new alarms.

Tests inject a store path; they do not rely solely on process-global env.

---

## 4. Domain model

Immutable value objects. Enums are explicit.

```python
class Weekday(IntEnum):  # MON=0 ... SUN=6
class ScheduleKind(StrEnum):  # ONCE, WEEKLY
class Decision(StrEnum):  # NOT_DUE, RING, MISSED, ALREADY_CLAIMED

@dataclass(frozen=True, slots=True)
class Alarm:
    id, local_time, timezone, kind, days, label, enabled,
    snooze_minutes, max_snoozes, sound

@dataclass(frozen=True, slots=True)
class Occurrence:
    alarm_id, scheduled_local, scheduled_utc, fold
    @property
    def key(self) -> str:  # "{id}:{YYYY-MM-DD}:{HH:MM}:{fold}"

@dataclass(frozen=True, slots=True)
class Snooze:
    id, alarm_id, until_utc, count

@dataclass(frozen=True, slots=True)
class ActiveRing:
    alarm_id, occurrence_key, started_at_utc, snoozes_used
```

Scheduler (pure):

```python
next_occurrence(alarm, now) -> Occurrence | None
evaluate_occurrence(occurrence, now, grace, claimed_keys) -> Decision
evaluate_snoozes(snoozes, now) -> list[Snooze]  # those that are due
```

No `datetime.now()`. Clock is injected.

### Persistence envelope

```json
{
  "schema_version": 2,
  "settings": {
    "format_24h": true,
    "theme": "tokyo-night",
    "grace_minutes": 5,
    "default_timezone": "Asia/Kolkata"
  },
  "alarms": [],
  "runtime": {
    "claimed_occurrences": [],
    "snoozes": [],
    "active_ring": null
  }
}
```

Load path: bytes → parse → validate envelope → migrate → validate domain.

Unknown future `schema_version` is an error. Do not silently drop unknown
top-level fields if they would change meaning; fail recoverable and leave the
original file untouched.

Schema 1 (if ever seen): missing `runtime` → empty runtime; missing `kind` with
empty days → ONCE; with days → WEEKLY.

---

## 5. Persistence and concurrency

Files under `platformdirs.user_data_dir("chime")` or `CHIME_DATA_DIR`:

```
alarms.json
alarms.json.bak
chime.lock
```

Atomic mutation:

```
acquire lock
  read + validate + migrate
  mutate in memory
  serialize deterministic JSON (sorted keys, trailing newline)
  write temp in SAME directory
  flush + fsync
  os.replace(temp, alarms.json)
  refresh backup
release lock
```

Corruption:

1. Do not overwrite a bad primary.
2. If backup is valid, load it and report recovery.
3. If both bad: CLI exits 2; TUI asks before starting empty.

Writers:

- TUI holds the lock for process lifetime (so CLI cannot sneak a write).
- CLI acquires for one transaction.
- Lock busy → `LockError`, exit 3, message `chime is already running`.

---

## 6. Scheduler loop (application)

Approx once per second, with injected clock:

1. Evaluate due snoozes → ring from snooze (does not re-claim the schedule key).
2. For each enabled alarm, compute next occurrence.
3. Evaluate against now and claimed keys.
4. On RING or MISSED: persist the claim **first**.
5. Only after durable claim: open ring UI (RING) or record missed (MISSED).
6. If persist fails: surface error, do not ring.

Exactly-once scope: at-most-once **after a successful persisted claim**.
Speaker output is best-effort.

---

## 7. Application use cases

Shared by CLI and TUI. Neither layer writes JSON.

```
create_alarm, update_alarm, delete_alarm, set_alarm_enabled, list_alarms
trigger_test_sound, process_clock_tick
snooze_active_ring, dismiss_active_ring
```

Validation lives here (authoritative) even if the TUI also gives immediate feedback.

Errors (typed):

`ValidationError`, `StorageError`, `CorruptStateError`, `MigrationError`,
`LockError`, `AudioUnavailableError`, `NotFoundError`.

CLI maps them to exit codes. TUI maps them to notifications. No bare
`except Exception` around the scheduler loop.

---

## 8. Testing strategy

Fake clock. Temp data dir. No wall-clock sleeps. No real audio in CI.

### Unit

Time/scheduler: exact time, ±1s, minute/hour/day/month/year rollover, leap day,
one-shot disable after dismiss, weekdays, disabled, grace boundary, outside grace,
backward/forward clock jump, spring-forward skip, fall-back once, snooze max,
already claimed, crash after claim / before persist.

Store: atomic save, backup, corrupt primary+valid backup, both corrupt, migrate,
unknown schema, deterministic JSON, lock contention.

Audio: backend detection, argv without shell, missing executable, cancel cleanup.

### Integration

`CLI → application → store → relaunch → list --json`
`TUI add → store → CLI list --json`
TUI lock held → CLI mutation exits 3.

### TUI

Textual `run_test` / Pilot: add form, toggle, quit-as-dismiss confirmation.

### Packaging

Wheel contains `beep.wav`. Domain modules do not import textual/typer/rich/platformdirs.
No `shell=True` in the tree. `--json` stdout is JSON-only.

---

## 9. Implementation order

1. This document + screen-recording script.
2. uv scaffold, pins, `chime --help`.
3. Domain: errors, models, time_utils, clock, scheduler + tests.
4. locking + store + tests.
5. application + CLI.
6. TUI + audio.
7. Screenshots, README, CI.
8. GitHub publish, then fix-loop until green.

Do not start with pixels. Start with time and durability.

---

## 10. Failure modes

| Failure | User-visible result | Recovery |
|---|---|---|
| App not running at alarm time | No ring (documented) | Open chime before the alarm |
| Crash after claim, before UI | No duplicate ring | Correct |
| Crash before claim persist | May ring once on relaunch if still in grace | Acceptable; at-most-once only after persist |
| Laptop wakes 2 min late | Ring | Grace |
| Laptop wakes 60 min late | Missed, no ring | Next occurrence for weekly |
| Corrupt JSON | Recover backup or fail | Never silent wipe |
| TUI + CLI write | CLI exit 3 | Close TUI |
| Missing Linux player | Next backend, then bell | doctor shows backend |
| Hung player | Bounded stop timeout | Ring UI still dismissable |

---

## 11. Security and privacy

- No shell interpolation of user input.
- Unix data dir mode 0o700 when creating.
- Do not log env dumps, full home paths, or raw JSON by default.
- Treat the state file as untrusted: types, ranges, enums, sizes.
- Bound collections so a huge file cannot explode memory (1 MiB cap).

---

## 12. Definition of Done

```
[ ] Scheduler decisions are deterministic under a fake clock
[ ] DST tests pass (spring-forward skip, fall-back once)
[ ] Crash/restart does not duplicate a claimed occurrence
[ ] Corrupt JSON never silently destroys data
[ ] CLI and TUI share the same use cases
[ ] Concurrent writes are blocked safely
[ ] Audio processes always clean up
[ ] --json stdout is machine-safe
[ ] Package assets work after wheel installation
[ ] Windows/macOS/Linux CI is present
[ ] Narrow terminal layout is usable
[ ] README states v1 requires the app to be running
[ ] README includes screenshots
[ ] Recording script exists for the builder's narration
[ ] Public GitHub repo vinothhacks/chime is updated
```

Ship only when the boxes above are green.

---

## 13. Implementation rules (must not be violated)

1. No `datetime.now()` in domain/scheduler code.
2. No naive datetimes crossing the application boundary.
3. No framework imports into the domain layer.
4. No direct JSON manipulation from CLI or TUI.
5. No `shell=True`.
6. No ring before durable occurrence claim.
7. No silent recovery from corrupt state.
8. No unbounded claimed-key growth.
9. No concurrent TUI/CLI writers.
10. No broad exception swallowing around the scheduler.
11. No Textual Web / React / database.
12. No new feature that expands the product boundary without updating the acceptance matrix.
