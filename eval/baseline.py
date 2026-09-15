"""Fixed-schedule baseline comparator (PRD Sec 5).

Retries on day 1/2/3 after failure regardless of cause - what a merchant
building the retry logic themselves would most likely do first, per PRD Sec
5's non-arbitrary comparator. Cause-agnostic by design, but still routed
through the same compliance rules as the allocator (peak-window avoidance,
attempt cap) - a baseline that violated compliance to look worse wouldn't be
a fair comparator. Same AllocatorDecision shape as pipeline.allocator so the
eval harness scores both identically.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pipeline.allocator import AllocatorDecision, CandidateWindow
from pipeline.compliance import (
    IST,
    MAX_RETRY_ATTEMPTS,
    at_most_one_success_per_cycle,
    attempts_within_cap,
    is_peak_window,
    shift_out_of_peak,
)
from pipeline.models import FailureCause

_DAY_OFFSETS_HOURS: tuple[int, ...] = (24, 48, 72)


def baseline_decide(
    cause: FailureCause, failure_time: datetime, attempts_used: int, billing_cycle_successes: int = 0
) -> AllocatorDecision:
    """Fixed-schedule policy: always retry on the next of day 1/2/3, cause-agnostic."""
    if failure_time.tzinfo is None:
        raise ValueError("baseline_decide requires a timezone-aware failure_time")
    if not attempts_within_cap(attempts_used):
        # Same fail-loud guard as pipeline.allocator.allocate(): attempts_used
        # indexes _DAY_OFFSETS_HOURS directly below, so a negative value would
        # silently wrap around to the wrong offset instead of erroring.
        raise ValueError(f"attempts_used={attempts_used} is outside the compliant range 0-{MAX_RETRY_ATTEMPTS}")
    if not at_most_one_success_per_cycle(billing_cycle_successes):
        raise ValueError(f"billing_cycle_successes={billing_cycle_successes} is outside the compliant range 0-1")

    attempts_remaining = max(MAX_RETRY_ATTEMPTS - attempts_used, 0)

    if billing_cycle_successes >= 1:
        # Same invariant as pipeline.allocator.allocate() - a fixed schedule
        # doesn't get to skip it just because it's cause-agnostic.
        return AllocatorDecision(
            action="stop",
            scheduled_at=None,
            candidates=[],
            attempts_used=attempts_used,
            attempts_remaining=attempts_remaining,
            billing_cycle_successes=billing_cycle_successes,
            reason="a successful debit already occurred this billing cycle - no further attempts permitted",
        )

    if attempts_remaining <= 0:
        return AllocatorDecision(
            action="stop",
            scheduled_at=None,
            candidates=[],
            attempts_used=attempts_used,
            attempts_remaining=0,
            billing_cycle_successes=billing_cycle_successes,
            reason=f"retry budget exhausted ({attempts_used}/{MAX_RETRY_ATTEMPTS} attempts used)",
        )

    hours = _DAY_OFFSETS_HOURS[attempts_used]
    label = f"day{attempts_used + 1}"
    naive = failure_time.astimezone(IST) + timedelta(hours=hours)

    candidates: list[CandidateWindow] = []
    if is_peak_window(naive):
        candidates.append(
            CandidateWindow(scheduled_at=naive, offset_label=label, score=0.0, compliant=False, rejected_reason="peak_window")
        )
        scheduled_at = shift_out_of_peak(naive)
        candidates.append(CandidateWindow(scheduled_at=scheduled_at, offset_label=f"{label}_shifted", score=1.0, compliant=True))
    else:
        scheduled_at = naive
        candidates.append(CandidateWindow(scheduled_at=scheduled_at, offset_label=label, score=1.0, compliant=True))

    assert not is_peak_window(scheduled_at), "baseline must never schedule inside a peak window"

    return AllocatorDecision(
        action="retry",
        scheduled_at=scheduled_at,
        candidates=candidates,
        attempts_used=attempts_used,
        attempts_remaining=attempts_remaining,
        billing_cycle_successes=billing_cycle_successes,
        reason=f"fixed schedule: {label}, cause ignored ({cause.value})",
    )
