"""Compliance invariant tests (PRD Sec 2, Sec 7 build step 2).

These are the claims most likely to be challenged - proven here before any
allocator logic is built (CLAUDE.md hard constraint).
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from pipeline.compliance import (
    IST,
    PEAK_WINDOWS,
    at_most_one_success_per_cycle,
    attempts_within_cap,
    is_peak_window,
    shift_out_of_peak,
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
    with pytest.raises(ValueError, match=r"^is_peak_window requires a timezone-aware datetime \(peak windows are IST\)$"):
        is_peak_window(naive)


def test_is_peak_window_accepts_other_named_timezones() -> None:
    # 11:00 US/Eastern == 20:30 IST same day - inside the evening peak window.
    dt = datetime(2026, 9, 3, 11, 0, tzinfo=ZoneInfo("America/New_York"))
    assert is_peak_window(dt) is True


@pytest.mark.parametrize("successes,expected", [(0, True), (1, True), (2, False), (5, False)])
def test_at_most_one_success_per_cycle(successes: int, expected: bool) -> None:
    assert at_most_one_success_per_cycle(successes) is expected


# Boundary tests added from mutation testing: each pins an edge that a
# one-character change (<= for <, > for >=) would otherwise slip past.
def _ist(h: int, m: int = 0, s: int = 0) -> datetime:
    return datetime(2026, 9, 1, h, m, s, tzinfo=IST)


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (_ist(9, 59, 59), False),
        (_ist(10, 0), True),
        (_ist(12, 59, 59), True),
        (_ist(13, 0), False),
        (_ist(16, 59, 59), False),
        (_ist(17, 0), True),
        (_ist(21, 29, 59), True),
        (_ist(21, 30), False),
    ],
)
def test_peak_window_edges_are_start_inclusive_end_exclusive(moment: datetime, expected: bool) -> None:
    assert is_peak_window(moment) is expected


def test_peak_window_converts_from_other_timezones() -> None:
    utc_0430 = datetime(2026, 9, 1, 4, 30, tzinfo=timezone.utc)  # 10:00 IST
    assert is_peak_window(utc_0430)
    assert not is_peak_window(utc_0430 - timedelta(seconds=1))


def test_peak_window_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match=r"^is_peak_window requires a timezone-aware datetime \(peak windows are IST\)$"):
        is_peak_window(datetime(2026, 9, 1, 11, 0))  # noqa: DTZ001 - naive on purpose


@pytest.mark.parametrize(("used", "ok"), [(-1, False), (0, True), (3, True), (4, False)])
def test_attempt_cap_edges(used: int, ok: bool) -> None:
    assert attempts_within_cap(used) is ok


@pytest.mark.parametrize(("n", "ok"), [(-1, False), (0, True), (1, True), (2, False)])
def test_one_success_per_cycle_edges(n: int, ok: bool) -> None:
    assert at_most_one_success_per_cycle(n) is ok


@pytest.mark.parametrize(("start", "end"), PEAK_WINDOWS)
def test_shift_out_of_peak_lands_exactly_on_window_end(start, end) -> None:
    inside = _ist(start.hour, start.minute, 30)
    shifted = shift_out_of_peak(inside)
    assert (shifted.hour, shifted.minute, shifted.second, shifted.microsecond) == (end.hour, end.minute, 0, 0)
    assert not is_peak_window(shifted)


def test_shift_out_of_peak_leaves_compliant_times_alone() -> None:
    moment = _ist(14, 15, 7)
    assert shift_out_of_peak(moment) == moment


@pytest.mark.parametrize(("start", "end"), PEAK_WINDOWS)
def test_shift_out_of_peak_edges(start, end) -> None:
    at_start = _ist(start.hour, start.minute)
    assert shift_out_of_peak(at_start).time() == end  # window start is inside the window
    at_end = _ist(end.hour, end.minute, 0)
    assert shift_out_of_peak(at_end) == at_end  # window end is already compliant


def test_shift_out_of_peak_clears_microseconds() -> None:
    moment = _ist(11, 0, 5).replace(microsecond=123456)
    assert shift_out_of_peak(moment).microsecond == 0
