"""Compliance invariant tests (PRD Sec 2, Sec 7 build step 2).

These are the claims most likely to be challenged - proven here before any
allocator logic is built (CLAUDE.md hard constraint).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from pipeline.compliance import (
    IST,
    at_most_one_success_per_cycle,
    attempts_within_cap,
    is_peak_window,
)


@pytest.mark.parametrize("attempts_used,expected", [(0, True), (1, True), (2, True), (3, True), (4, False), (10, False)])
def test_attempts_within_cap_never_exceeds_three(attempts_used: int, expected: bool) -> None:
    assert attempts_within_cap(attempts_used) is expected


@pytest.mark.parametrize(
    "hhmm,expected",
    [
        ("09:59", False),
        ("10:00", True),
        ("11:30", True),
        ("12:59", True),
        ("13:00", False),
        ("13:01", False),
        ("16:59", False),
        ("17:00", True),
        ("19:00", True),
        ("21:29", True),
        ("21:30", False),
        ("21:31", False),
        ("00:00", False),
        ("23:59", False),
    ],
)
def test_is_peak_window_boundaries_in_ist(hhmm: str, expected: bool) -> None:
    dt = datetime.strptime(f"2026-09-03 {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    assert is_peak_window(dt) is expected


def test_is_peak_window_converts_non_ist_input_correctly() -> None:
    # 07:30 UTC == 13:00 IST (UTC+5:30) - the peak window's excluded end edge.
    dt_utc = datetime(2026, 9, 3, 7, 30, tzinfo=timezone.utc)
    assert is_peak_window(dt_utc) is False
    # 07:29 UTC == 12:59 IST - one minute inside the peak window.
    dt_utc = datetime(2026, 9, 3, 7, 29, tzinfo=timezone.utc)
    assert is_peak_window(dt_utc) is True


def test_is_peak_window_rejects_naive_datetime() -> None:
    naive = datetime(2026, 9, 3, 11, 0)  # noqa: DTZ001 - deliberately naive, testing rejection
    with pytest.raises(ValueError, match="timezone-aware"):
        is_peak_window(naive)


def test_is_peak_window_accepts_other_named_timezones() -> None:
    # 11:00 US/Eastern == 20:30 IST same day - inside the evening peak window.
    dt = datetime(2026, 9, 3, 11, 0, tzinfo=ZoneInfo("America/New_York"))
    assert is_peak_window(dt) is True


@pytest.mark.parametrize("successes,expected", [(0, True), (1, True), (2, False), (5, False)])
def test_at_most_one_success_per_cycle(successes: int, expected: bool) -> None:
    assert at_most_one_success_per_cycle(successes) is expected
