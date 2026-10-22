from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from .models import DateWindow


class WindowSplitError(ValueError):
    """Raised when a date window cannot be split any further."""


def inclusive_days(window: DateWindow) -> int:
    return (window.end - window.start).days + 1


def can_split(window: DateWindow) -> bool:
    return inclusive_days(window) >= 2


def split_window(window: DateWindow) -> tuple[DateWindow, DateWindow]:
    """Split an inclusive window into two contiguous inclusive halves.

    Example: 2026-01-01 → 2026-01-31 becomes
    2026-01-01 → 2026-01-15 and 2026-01-16 → 2026-01-31.
    """
    if not can_split(window):
        raise WindowSplitError(
            "Cannot split a {}-day window starting {}".format(
                inclusive_days(window), window.start.isoformat()
            )
        )
    half = inclusive_days(window) // 2
    left_end = window.start + timedelta(days=half - 1)
    right_start = left_end + timedelta(days=1)
    return DateWindow(window.start, left_end), DateWindow(right_start, window.end)


def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
