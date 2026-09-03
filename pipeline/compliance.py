"""Compliance invariants (PRD Sec 7 build step 2, Sec 2).

Pure predicate functions with no dependency on the allocator - these lock the
contract every later stage (allocator, baseline, eval harness) must satisfy.
Unit-tested before any allocation logic exists, per CLAUDE.md.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

# NPCI cap: 1 original attempt + max 3 retries per mandate (PRD Sec 2).
MAX_RETRY_ATTEMPTS = 3

# NPCI peak windows are defined in India wall-clock time.
IST = ZoneInfo("Asia/Kolkata")

# Peak windows a retry must never be scheduled inside (PRD Sec 2). Each is
# [start, end) - start inclusive, end exclusive - in IST.
PEAK_WINDOWS: tuple[tuple[time, time], ...] = (
    (time(10, 0), time(13, 0)),
    (time(17, 0), time(21, 30)),
)


def attempts_within_cap(attempts_used: int) -> bool:
    """True if attempts_used does not exceed the NPCI retry cap (PRD Sec 2)."""
    return 0 <= attempts_used <= MAX_RETRY_ATTEMPTS


def is_peak_window(dt: datetime) -> bool:
    """True if dt falls inside an NPCI peak window (PRD Sec 2).

    Requires a timezone-aware datetime - peak windows are IST wall-clock, and
    silently treating a naive datetime as IST would misclassify any caller
    working in UTC (a real risk on a compliance-critical path).
    """
    if dt.tzinfo is None:
        raise ValueError("is_peak_window requires a timezone-aware datetime (peak windows are IST)")
    t = dt.astimezone(IST).time()
    return any(start <= t < end for start, end in PEAK_WINDOWS)


def at_most_one_success_per_cycle(successes_in_cycle: int) -> bool:
    """True if at most one successful debit has occurred this billing cycle (PRD Sec 2)."""
    return 0 <= successes_in_cycle <= 1
