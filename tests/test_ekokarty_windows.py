from datetime import date

import pytest

from src.ekokarty.models import DateWindow
from src.ekokarty.windows import WindowSplitError, can_split, split_window


def test_january_window_splits_on_the_documented_boundary() -> None:
    left, right = split_window(DateWindow(date(2026, 1, 1), date(2026, 1, 31)))
    assert (left.start, left.end) == (date(2026, 1, 1), date(2026, 1, 15))
    assert (right.start, right.end) == (date(2026, 1, 16), date(2026, 1, 31))


def test_two_day_window_splits_into_single_days() -> None:
    left, right = split_window(DateWindow(date(2026, 1, 1), date(2026, 1, 2)))
    assert (left.start, left.end) == (date(2026, 1, 1), date(2026, 1, 1))
    assert (right.start, right.end) == (date(2026, 1, 2), date(2026, 1, 2))


def test_single_day_cannot_be_split() -> None:
    window = DateWindow(date(2026, 1, 1), date(2026, 1, 1))
    assert can_split(window) is False
    with pytest.raises(WindowSplitError):
        split_window(window)
