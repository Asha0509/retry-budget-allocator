"""Property-based fuzzing of Stage 5 allocation (PRD Sec 4).

Extends fuzzing coverage beyond Stage 2 classification
(tests/test_classify_fuzz.py, the only stage it covered as of
2026-09-15) to the allocator - the actual money-spending decision, and
the stage the fail-open bug in docs/build-log.md (2026-09-14) was found
in. Generates a wide range of failure times and attempt counts rather
than the handful of hand-picked values the existing unit tests use, and
asserts the same invariants the manual audit and the regression tests
already check, now over a much larger generated space.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.allocator import allocate
from pipeline.compliance import MAX_RETRY_ATTEMPTS, is_peak_window
from pipeline.models import FailureCause

_failure_times = st.datetimes(
    min_value=datetime(2020, 1, 1),  # noqa: DTZ001 - hypothesis requires naive bounds here; tzinfo comes from `timezones=` below
    max_value=datetime(2035, 1, 1),  # noqa: DTZ001
    timezones=st.just(timezone.utc),
)
_valid_attempts_used = st.integers(min_value=0, max_value=MAX_RETRY_ATTEMPTS - 1)
_retry_causes = st.sampled_from([FailureCause.INSUFFICIENT_FUNDS, FailureCause.BANK_TECHNICAL])
_stop_causes = st.sampled_from(
    [FailureCause.MANDATE_REVOKED, FailureCause.MANDATE_EXPIRED, FailureCause.AMOUNT_EXCEEDS_MANDATE]
)


@given(cause=_retry_causes, failure_time=_failure_times, attempts_used=_valid_attempts_used)
@settings(max_examples=500)
def test_allocate_never_schedules_inside_a_peak_window(cause, failure_time, attempts_used) -> None:
    decision = allocate(cause, failure_time, attempts_used)
    if decision.action == "retry":
        assert decision.scheduled_at is not None
        assert not is_peak_window(decision.scheduled_at)


@given(cause=st.sampled_from(list(FailureCause)), failure_time=_failure_times, attempts_used=_valid_attempts_used)
@settings(max_examples=500)
def test_allocate_never_raises_on_any_valid_input(cause, failure_time, attempts_used) -> None:
    # No-crash property: a money-path stage must handle any in-range
    # combination of cause/time/attempts without an exception.
    decision = allocate(cause, failure_time, attempts_used)
    assert decision.attempts_used == attempts_used
    assert 0 <= decision.attempts_remaining <= MAX_RETRY_ATTEMPTS


@given(cause=_stop_causes, failure_time=_failure_times, attempts_used=st.integers(min_value=0, max_value=MAX_RETRY_ATTEMPTS))
@settings(max_examples=300)
def test_structurally_unrecoverable_causes_never_retry_regardless_of_timing(cause, failure_time, attempts_used) -> None:
    decision = allocate(cause, failure_time, attempts_used)
    assert decision.action == "stop"
    assert decision.scheduled_at is None


@given(
    cause=st.sampled_from(list(FailureCause)),
    failure_time=_failure_times,
    attempts_used=st.integers(min_value=-1000, max_value=1000).filter(lambda x: not (0 <= x <= MAX_RETRY_ATTEMPTS)),
)
@settings(max_examples=300)
def test_out_of_range_attempts_used_always_fails_loud_never_silent(cause, failure_time, attempts_used) -> None:
    # Regression property for the exact bug in docs/build-log.md
    # (2026-09-14): out-of-range attempts_used must raise, over a wide
    # generated range, not just the 4 hand-picked values in
    # tests/test_allocator.py.
    with pytest.raises(ValueError, match="outside the compliant range"):
        allocate(cause, failure_time, attempts_used)
