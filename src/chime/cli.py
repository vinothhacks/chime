"""Typer CLI. Maps domain errors to exit codes. JSON only on stdout for --json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import typer

from chime import __version__
from chime.application import Application
from chime.clock import SystemClock
from chime.config import data_dir, default_timezone
from chime.errors import ChimeError, LockError, ValidationError
from chime.locking import ProcessLock
from chime.models import ScheduleKind, Weekday
from chime.store import Store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    invoke_without_command=True,
    pretty_exceptions_enable=False,
    help="Terminal-native alarm clock. The app must be running to ring.",
)


def _fail(exc: BaseException) -> None:
    message = str(exc) or exc.__class__.__name__
    sys.stderr.write(f"error: {message}\n")
    code = getattr(exc, "exit_code", 1)
    raise typer.Exit(code)


def _application(data_dir_override: Path | None) -> Application:
    if data_dir_override is not None:
        os.environ["CHIME_DATA_DIR"] = str(data_dir_override)
    path = data_dir()
    store = Store(path, ProcessLock(path / "chime.lock"))
    return Application(store, SystemClock())


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    data_dir_option: Path | None = typer.Option(
        None,
        "--data-dir",
        help="Override the application data directory (also CHIME_DATA_DIR).",
        envvar="CHIME_DATA_DIR",
    ),
    version: bool = typer.Option(False, "--version", help="Show version and exit."),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit(0)
    ctx.obj = {"data_dir": data_dir_option}
    if ctx.invoked_subcommand is None:
        _run_tui(data_dir_option)


def _run_tui(data_dir_override: Path | None) -> None:
    from chime.tui.app import run_tui

    try:
        run_tui(data_dir_override)
    except LockError as exc:
        _fail(exc)
    except ChimeError as exc:
        _fail(exc)


@app.command("add")
def add_cmd(
    ctx: typer.Context,
    time: str = typer.Argument(..., help="Alarm time, e.g. 07:30, 730, 7:30pm"),
    once: bool = typer.Option(False, "--once", help="One-shot alarm."),
    days: str | None = typer.Option(
        None, "--days", help="Weekdays: weekdays, weekends, sat,sun, ..."
    ),
    label: str = typer.Option("", "--label", "-l", help="Short label."),
    timezone: str | None = typer.Option(None, "--timezone", "-z"),
    snooze: int = typer.Option(9, "--snooze"),
    max_snoozes: int = typer.Option(3, "--max-snoozes"),
) -> None:
    try:
        if once and days:
            raise ValidationError("use --once or --days, not both")
        is_once = once or not days
        alarm = _application(ctx.obj["data_dir"]).create_alarm(
            time,
            once=is_once,
            days_raw=None if is_once else days,
            label=label,
            timezone=timezone,
            snooze_minutes=snooze,
            max_snoozes=max_snoozes,
        )
    except ChimeError as exc:
        _fail(exc)
    typer.echo(f"added {alarm.id}  {alarm.local_time}  {alarm.label or '(no label)'}")


@app.command("list")
def list_cmd(
    ctx: typer.Context,
    as_json: bool = typer.Option(False, "--json", help="Machine-readable JSON on stdout."),
) -> None:
    try:
        state = _application(ctx.obj["data_dir"]).load_state()
    except ChimeError as exc:
        _fail(exc)
    if as_json:
        from chime.store import serialize_alarm

        typer.echo(
            json.dumps(
                {"alarms": [serialize_alarm(item) for item in state.alarms]},
                indent=2,
                sort_keys=True,
            )
        )
        return
    if not state.alarms:
        typer.echo("no alarms")
        return
    for alarm in state.alarms:
        typer.echo(_format_alarm(alarm, state.settings.format_24h))


@app.command("rm")
def rm_cmd(ctx: typer.Context, ident: str = typer.Argument(...)) -> None:
    try:
        _application(ctx.obj["data_dir"]).delete_alarm(ident)
    except ChimeError as exc:
        _fail(exc)
    typer.echo(f"removed {ident}")


@app.command("on")
def on_cmd(ctx: typer.Context, ident: str = typer.Argument(...)) -> None:
    try:
        alarm = _application(ctx.obj["data_dir"]).set_alarm_enabled(ident, True)
    except ChimeError as exc:
        _fail(exc)
    typer.echo(f"{alarm.id} ON")


@app.command("off")
def off_cmd(ctx: typer.Context, ident: str = typer.Argument(...)) -> None:
    try:
        alarm = _application(ctx.obj["data_dir"]).set_alarm_enabled(ident, False)
    except ChimeError as exc:
        _fail(exc)
    typer.echo(f"{alarm.id} OFF")


@app.command("test-sound")
def test_sound_cmd() -> None:
    import asyncio

    from chime.sound import DefaultAudioPlayer

    async def _run() -> None:
        player = DefaultAudioPlayer()
        await player.start("default")
        await asyncio.sleep(1.5)
        await player.stop()

    try:
        asyncio.run(_run())
    except ChimeError as exc:
        _fail(exc)
    typer.echo("played bundled beep (best-effort)")


@app.command("doctor")
def doctor_cmd(ctx: typer.Context) -> None:
    import platform

    from chime.sound import beep_exists, detect_backend

    path = ctx.obj["data_dir"] or data_dir()
    if ctx.obj["data_dir"] is not None:
        os.environ["CHIME_DATA_DIR"] = str(ctx.obj["data_dir"])
        path = data_dir()
    lock_path = path / "chime.lock"
    lock = ProcessLock(lock_path)
    lock_status = "free"
    try:
        if lock.acquire(blocking=False):
            lock.release()
        else:
            lock_status = "held"
    except LockError:
        lock_status = "held"
    json_health = "missing"
    primary = path / "alarms.json"
    if primary.exists():
        try:
            Store(path, lock).load()
            json_health = "ok"
        except ChimeError as exc:
            json_health = f"error: {exc}"
    lines = [
        f"chime_version: {__version__}",
        f"python: {sys.version.split()[0]}",
        f"platform: {platform.system()} {platform.release()}",
        f"terminal: {os.environ.get('TERM', 'unknown')}",
        f"data_dir: {path}",
        f"lock: {lock_status}",
        f"json: {json_health}",
        f"timezone: {default_timezone()}",
        f"audio_backend: {detect_backend()}",
        f"bundled_wav: {'yes' if beep_exists() else 'no'}",
    ]
    typer.echo("\n".join(lines))


def _format_alarm(alarm: object, format_24h: bool) -> str:
    from chime.models import Alarm

    assert isinstance(alarm, Alarm)
    days = _day_marks(alarm)
    state = "ON" if alarm.enabled else "OFF"
    kind = "once" if alarm.kind is ScheduleKind.ONCE else "weekly"
    label = alarm.label or "-"
    return f"{alarm.id}  {alarm.local_time}  {days}  {label}  [{state}]  {kind}"


def _day_marks(alarm: object) -> str:
    from chime.models import Alarm

    assert isinstance(alarm, Alarm)
    if alarm.kind is ScheduleKind.ONCE:
        return "once     "
    names = ["M", "T", "W", "T", "F", "S", "S"]
    marks = []
    enabled = {int(day) for day in alarm.days}
    for idx, name in enumerate(names):
        marks.append(name if idx in enabled else ".")
    return " ".join(marks)


WEEKDAYS = Weekday  # re-export for tests that import CLI helpers
