"""Unit tests for the fixed-schedule baseline comparator (PRD Sec 5, Sec 7 build step 6)."""

from datetime import datetime

import pytest

from eval.baseline import baseline_decide
from pipeline.compliance import IST, MAX_RETRY_ATTEMPTS, is_peak_window
from pipeline.models import FailureCause


def _dt(hhmm: str, day: int = 3) -> datetime:
    return datetime.strptime(f"2026-09-{day:02d} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)


@pytest.mark.parametrize("cause", list(FailureCause))
def test_always_retries_regardless_of_cause_while_budget_remains(cause: FailureCause) -> None:
    decision = baseline_decide(cause, _dt("08:00"), attempts_used=0)
    assert decision.action == "retry"


@pytest.mark.parametrize("attempts_used,expected_label", [(0, "day1"), (1, "day2"), (2, "day3")])
def test_schedules_the_next_fixed_day_offset(attempts_used: int, expected_label: str) -> None:
    decision = baseline_decide(FailureCause.MANDATE_REVOKED, _dt("08:00"), attempts_used=attempts_used)
    chosen = next(c for c in decision.candidates if c.scheduled_at == decision.scheduled_at)
    assert chosen.offset_label == expected_label


def test_never_stops_early_even_for_unrecoverable_causes() -> None:
    # The whole point of the comparison: baseline burns attempts a cause-aware allocator wouldn't.
    for attempts_used in range(MAX_RETRY_ATTEMPTS):
        decision = baseline_decide(FailureCause.MANDATE_REVOKED, _dt("08:00"), attempts_used=attempts_used)
        assert decision.action == "retry"


def test_exhausted_budget_stops() -> None:
    decision = baseline_decide(FailureCause.INSUFFICIENT_FUNDS, _dt("08:00"), attempts_used=MAX_RETRY_ATTEMPTS)
    assert decision.action == "stop"
    assert decision.scheduled_at is None


def test_never_schedules_in_a_peak_window() -> None:
    # day-offsets are exact multiples of 24h from a peak-window failure time,
    # so every naive candidate would land in the same peak window.
    for attempts_used in range(MAX_RETRY_ATTEMPTS):
        decision = baseline_decide(FailureCause.INSUFFICIENT_FUNDS, _dt("11:00"), attempts_used=attempts_used)
        assert not is_peak_window(decision.scheduled_at)
        rejected = [c for c in decision.candidates if not c.compliant]
        assert len(rejected) == 1
        assert rejected[0].rejected_reason == "peak_window"


def test_requires_timezone_aware_failure_time() -> None:
    naive = datetime(2026, 9, 3, 8, 0)  # noqa: DTZ001 - deliberately naive, testing rejection
    with pytest.raises(ValueError, match="timezone-aware"):
        baseline_decide(FailureCause.INSUFFICIENT_FUNDS, naive, attempts_used=0)
