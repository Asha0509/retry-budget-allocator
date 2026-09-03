"""Unit tests for Stage 5 budget allocation (PRD Sec 4, Sec 7 build step 4)."""

from datetime import datetime

import pytest

from pipeline.allocator import allocate, run_allocation
from pipeline.compliance import MAX_RETRY_ATTEMPTS, is_peak_window
from pipeline.models import FailureCause, FundingWindowEstimate


def _dt(hhmm: str, day: int = 3) -> datetime:
    from pipeline.compliance import IST

    return datetime.strptime(f"2026-09-{day:02d} {hhmm}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)


@pytest.mark.parametrize(
    "cause", [FailureCause.MANDATE_REVOKED, FailureCause.MANDATE_EXPIRED, FailureCause.AMOUNT_EXCEEDS_MANDATE]
)
def test_structurally_unrecoverable_causes_stop_and_spend_nothing(cause: FailureCause) -> None:
    decision = allocate(cause, _dt("08:00"), attempts_used=0)
    assert decision.action == "stop"
    assert decision.scheduled_at is None
    assert decision.candidates == []


def test_afa_required_notifies_never_retries() -> None:
    decision = allocate(FailureCause.AFA_REQUIRED, _dt("08:00"), attempts_used=0)
    assert decision.action == "notify"
    assert decision.candidates == []


def test_insufficient_funds_with_budget_retries_and_returns_all_candidates() -> None:
    decision = allocate(FailureCause.INSUFFICIENT_FUNDS, _dt("08:00"), attempts_used=0)
    assert decision.action == "retry"
    assert decision.scheduled_at is not None
    assert not is_peak_window(decision.scheduled_at)
    # 3 safe-spacing offsets scored, none rejected here (08:00 + 24/72/168h avoids both windows)
    assert len(decision.candidates) == 3
    assert all(c.compliant for c in decision.candidates)


def test_exhausted_budget_stops_regardless_of_cause() -> None:
    decision = allocate(FailureCause.INSUFFICIENT_FUNDS, _dt("08:00"), attempts_used=MAX_RETRY_ATTEMPTS)
    assert decision.action == "stop"
    assert decision.scheduled_at is None
    assert decision.attempts_remaining == 0


def test_peak_window_candidate_is_scored_and_rejected_not_silently_dropped() -> None:
    # 24h/72h/168h are all exact multiples of 24h, so the naive candidate
    # keeps the failure's time-of-day at every offset. A failure at 10:30
    # (inside the first peak window) means all three naive candidates land
    # in that same window - each must appear rejected, not silently dropped.
    failure_time = _dt("10:30")
    decision = allocate(FailureCause.BANK_TECHNICAL, failure_time, attempts_used=0)
    rejected = [c for c in decision.candidates if not c.compliant]
    assert len(rejected) == 3
    assert {c.offset_label for c in rejected} == {"24h", "72h", "168h"}
    assert all(c.rejected_reason == "peak_window" for c in rejected)
    assert all(is_peak_window(c.scheduled_at) for c in rejected)
    # each rejected offset still has a compliant shifted alternative scored
    shifted = [c for c in decision.candidates if c.offset_label.endswith("_shifted")]
    assert len(shifted) == 3
    assert all(c.compliant and not is_peak_window(c.scheduled_at) for c in shifted)
    # the chosen action never lands in a peak window
    assert not is_peak_window(decision.scheduled_at)


def test_bank_technical_prefers_earliest_compliant_offset() -> None:
    decision = allocate(FailureCause.BANK_TECHNICAL, _dt("08:00"), attempts_used=0)
    assert decision.action == "retry"
    chosen = next(c for c in decision.candidates if c.scheduled_at == decision.scheduled_at)
    assert chosen.offset_label == "24h"


def test_candidate_inside_likely_funding_window_scores_higher() -> None:
    """This is the seam step 9 (funding_window.py) plugs into - a non-fallback
    estimate should visibly change candidate scoring, not just the fallback path."""
    failure_time = _dt("08:00")
    window_start = _dt("08:00", day=6)  # the 72h candidate
    window_end = _dt("08:00", day=7)
    estimate = FundingWindowEstimate(likely_window=(window_start, window_end), confidence=0.9, used_fallback=False)

    boosted = allocate(FailureCause.INSUFFICIENT_FUNDS, failure_time, attempts_used=0, funding_estimate=estimate)
    baseline = allocate(FailureCause.INSUFFICIENT_FUNDS, failure_time, attempts_used=0)

    boosted_72h = next(c for c in boosted.candidates if c.offset_label == "72h")
    baseline_72h = next(c for c in baseline.candidates if c.offset_label == "72h")
    assert boosted_72h.score == pytest.approx(baseline_72h.score * 1.5)
    # offsets outside the likely window are unaffected
    boosted_24h = next(c for c in boosted.candidates if c.offset_label == "24h")
    baseline_24h = next(c for c in baseline.candidates if c.offset_label == "24h")
    assert boosted_24h.score == baseline_24h.score


def test_successive_attempts_pick_distinct_windows_not_the_same_one_again() -> None:
    """Regression: candidate generation doesn't depend on attempts_used (it's
    always the same 3 safe-spacing offsets from the original failure), so a
    second attempt must not re-choose the exact same window the first attempt
    already tried and failed."""
    failure_time = _dt("08:00")
    scheduled_times = set()
    offset_labels = []
    for attempts_used in range(3):
        decision = allocate(FailureCause.INSUFFICIENT_FUNDS, failure_time, attempts_used=attempts_used)
        assert decision.action == "retry"
        scheduled_times.add(decision.scheduled_at)
        offset_labels.append(decision.reason)
    assert len(scheduled_times) == 3, f"expected 3 distinct scheduled times, got {scheduled_times}"


def test_attempt_order_follows_descending_score() -> None:
    failure_time = _dt("08:00")
    decisions = [allocate(FailureCause.BANK_TECHNICAL, failure_time, attempts_used=i) for i in range(3)]
    scores = []
    for d in decisions:
        chosen = next(c for c in d.candidates if c.scheduled_at == d.scheduled_at)
        scores.append(chosen.score)
    assert scores == sorted(scores, reverse=True)


def test_never_exceeds_attempt_cap_across_causes() -> None:
    for cause in FailureCause:
        for attempts_used in range(MAX_RETRY_ATTEMPTS + 3):
            decision = allocate(cause, _dt("08:00"), attempts_used=attempts_used)
            if attempts_used >= MAX_RETRY_ATTEMPTS:
                assert decision.action == "stop"


def test_allocate_requires_timezone_aware_failure_time() -> None:
    naive = datetime(2026, 9, 3, 8, 0)  # noqa: DTZ001 - deliberately naive, testing rejection
    with pytest.raises(ValueError, match="timezone-aware"):
        allocate(FailureCause.INSUFFICIENT_FUNDS, naive, attempts_used=0)


def test_run_allocation_returns_stage_trace() -> None:
    decision, trace = run_allocation(FailureCause.INSUFFICIENT_FUNDS, _dt("08:00"), attempts_used=0)
    assert trace.stage == "allocate"
    assert decision.action == "retry"
    assert "action=retry" in trace.output_summary
