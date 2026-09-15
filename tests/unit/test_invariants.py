from __future__ import annotations

import ast
from pathlib import Path

DOMAIN_FILES = [
    "errors.py",
    "models.py",
    "clock.py",
    "time_utils.py",
    "scheduler.py",
]
FORBIDDEN = {"textual", "typer", "rich", "platformdirs"}
SRC = Path(__file__).resolve().parents[2] / "src" / "chime"


def test_domain_does_not_import_frameworks() -> None:
    for name in DOMAIN_FILES:
        tree = ast.parse((SRC / name).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(FORBIDDEN), f"{name} imports {imported & FORBIDDEN}"


def test_no_shell_true() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "shell=True" in text or "shell = True" in text:
            offenders.append(str(path))
    assert offenders == []


def test_no_datetime_now_in_scheduler() -> None:
    text = (SRC / "scheduler.py").read_text(encoding="utf-8")
    assert "datetime.now(" not in text.split('"""', 2)[-1]
    assert "datetime.utcnow" not in text


def test_beep_resource_exists() -> None:
    from chime.sound import beep_exists

    assert beep_exists()
