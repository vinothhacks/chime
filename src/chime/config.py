"""Paths and env overrides. Not imported by the pure scheduler."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def data_dir() -> Path:
    override = os.environ.get("CHIME_DATA_DIR")
    if override:
        return Path(override)
    from platformdirs import user_data_dir

    return Path(user_data_dir("chime", appauthor=False))


def default_timezone() -> str:
    override = os.environ.get("CHIME_TIMEZONE")
    if override:
        try:
            ZoneInfo(override)
        except (ZoneInfoNotFoundError, ValueError):
            return "UTC"
        return override
    local = datetime.now().astimezone()
    tzinfo = local.tzinfo
    key = getattr(tzinfo, "key", None)
    if isinstance(key, str) and key:
        return key
    return "UTC"
