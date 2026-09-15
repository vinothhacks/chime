from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from chime.cli import app

runner = CliRunner()


def test_cli_add_list_json_roundtrip(data_dir: Path) -> None:
    result = runner.invoke(
        app, ["--data-dir", str(data_dir), "add", "07:30", "--once", "-l", "Gym"]
    )
    assert result.exit_code == 0, result.output
    listed = runner.invoke(app, ["--data-dir", str(data_dir), "list", "--json"])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.stdout)
    assert payload["alarms"][0]["label"] == "Gym"
    assert payload["alarms"][0]["local_time"] == "07:30"
    human = runner.invoke(app, ["--data-dir", str(data_dir), "list"])
    assert "Gym" in human.stdout
    assert human.stdout.strip() == human.stdout.strip()


def test_cli_weekdays_and_weekends(data_dir: Path) -> None:
    runner.invoke(
        app, ["--data-dir", str(data_dir), "add", "07:30", "--days", "weekdays", "-l", "Gym"]
    )
    runner.invoke(
        app, ["--data-dir", str(data_dir), "add", "08:15", "--days", "sat,sun", "-l", "Weekend"]
    )
    listed = runner.invoke(app, ["--data-dir", str(data_dir), "list", "--json"])
    payload = json.loads(listed.stdout)
    kinds = {item["label"]: item["days"] for item in payload["alarms"]}
    assert kinds["Gym"] == [0, 1, 2, 3, 4]
    assert kinds["Weekend"] == [5, 6]


def test_cli_on_off_rm(data_dir: Path) -> None:
    add = runner.invoke(app, ["--data-dir", str(data_dir), "add", "09:00", "--once", "-l", "X"])
    ident = add.stdout.split()[1]
    off = runner.invoke(app, ["--data-dir", str(data_dir), "off", ident])
    assert off.exit_code == 0
    listed = json.loads(runner.invoke(app, ["--data-dir", str(data_dir), "list", "--json"]).stdout)
    assert listed["alarms"][0]["enabled"] is False
    on = runner.invoke(app, ["--data-dir", str(data_dir), "on", ident])
    assert on.exit_code == 0
    rm = runner.invoke(app, ["--data-dir", str(data_dir), "rm", ident])
    assert rm.exit_code == 0
    listed = json.loads(runner.invoke(app, ["--data-dir", str(data_dir), "list", "--json"]).stdout)
    assert listed["alarms"] == []


def test_cli_json_stdout_is_only_json(data_dir: Path) -> None:
    runner.invoke(app, ["--data-dir", str(data_dir), "add", "07:30", "--once", "-l", "Gym"])
    listed = runner.invoke(app, ["--data-dir", str(data_dir), "list", "--json"])
    json.loads(listed.stdout)
    assert not listed.stdout.lstrip().startswith("error")


def test_cli_validation_exit_code(data_dir: Path) -> None:
    result = runner.invoke(app, ["--data-dir", str(data_dir), "add", "25:00", "--once"])
    assert result.exit_code == 1


def test_cli_lock_error(data_dir: Path) -> None:
    from chime.locking import ProcessLock

    lock = ProcessLock(data_dir / "chime.lock")
    assert lock.acquire(blocking=False)
    try:
        result = runner.invoke(
            app, ["--data-dir", str(data_dir), "add", "07:30", "--once", "-l", "Gym"]
        )
        assert result.exit_code == 3
    finally:
        lock.release()


def test_doctor_runs(data_dir: Path) -> None:
    result = runner.invoke(app, ["--data-dir", str(data_dir), "doctor"])
    assert result.exit_code == 0
    assert "chime_version:" in result.stdout
    assert "audio_backend:" in result.stdout
