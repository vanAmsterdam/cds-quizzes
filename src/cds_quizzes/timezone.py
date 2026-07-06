from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


APP_TIMEZONE_NAME = "Europe/Amsterdam"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)


def amsterdam_now() -> datetime:
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)


def to_amsterdam_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(APP_TIMEZONE).replace(tzinfo=None)
