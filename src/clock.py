"""Default clock providers for transaction application workflows."""

from datetime import date, datetime, timezone
from typing import Callable

TodayProvider = Callable[[], date]
UtcNowProvider = Callable[[], datetime]


def local_today() -> date:
    """Return today's date in the application's local timezone."""
    return date.today()


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)
