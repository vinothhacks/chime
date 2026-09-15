from __future__ import annotations

from chime.config import INDIA_TZ, default_timezone


def test_default_timezone_is_india(monkeypatch) -> None:
    monkeypatch.delenv("CHIME_TIMEZONE", raising=False)
    assert default_timezone() == INDIA_TZ
    assert INDIA_TZ == "Asia/Kolkata"


def test_env_override(monkeypatch) -> None:
    monkeypatch.setenv("CHIME_TIMEZONE", "UTC")
    assert default_timezone() == "UTC"
