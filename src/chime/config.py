"""Paths and env overrides. Not imported by the pure scheduler."""

from __future__ import annotations

import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Product clock is India only. No world-clock strip in v1.
INDIA_TZ = "Asia/Kolkata"


def data_dir() -> Path:
    override = os.environ.get("CHIME_DATA_DIR")
    if override:
        return Path(override)
    from platformdirs import user_data_dir

    return Path(user_data_dir("chime", appauthor=False))


def default_timezone() -> str:
    """IANA zone for new alarms and the TUI clock.

    Defaults to India (Asia/Kolkata). Windows often has no IANA key, so we do
    not fall back to UTC. Tests may set CHIME_TIMEZONE.
    """
    override = os.environ.get("CHIME_TIMEZONE")
    if override:
        try:
            ZoneInfo(override)
        except (ZoneInfoNotFoundError, ValueError):
            return INDIA_TZ
        return override
    return INDIA_TZ
