"""Stage 5 - budget allocation (PRD Sec 4).

Given a classified cause, how many retry attempts remain, and a funding-
window estimate, decides notify / retry-at-T / stop. Scores every candidate
window in the safe-spacing schedule (24h/72h/7d - PRD Sec 2) and returns all
of them with rejection reasons, not just the winner (Sec 6.1 hard
constraint). Never imports eval.outcome_model - its own scoring is a simple,
declared heuristic over recoverability and offset, kept deliberately separate
from the outcome model so evaluation against that model isn't circular (Sec
5.1).

Funding-window inference (Stage 4, build step 9) doesn't exist yet - this
stage is built and proven against the documented safe-spacing fallback first
(PRD build order deliberately sequences it this way). `funding_estimate`
defaults to that fallback; step 9 passes a real `FundingWindowEstimate` in
without any change needed here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel

from pipeline.compliance import (
    IST,
    MAX_RETRY_ATTEMPTS,
    is_peak_window,
    shift_out_of_peak,
)
from pipeline.models import (
    Action,
    FailureCause,
    FundingWindowEstimate,
    StageTrace,
    run_stage,
)
from pipeline.priors import get_prior

# Safe-spacing schedule (PRD Sec 2): 24h / 72h / 7 days.
_SAFE_SPACING_HOURS: tuple[int, ...] = (24, 72, 168)

# Cause-specific preference over the safe-spacing offsets, absent any real
# funding signal (used only while funding_estimate.used_fallback is True):
# a declared heuristic, not a probability - the real probability model lives
# in eval/outcome_model.py and this module never imports it.
#
# bank_technical resolves fast and keeps decaying, so sooner strictly scores
# higher - a monotonic falloff matches a monotonic decay.
#
# insufficient_funds has no known funding date, so 72h (the PRD Sec 2
# "safe-spacing" middle checkpoint - a reasonable few-days guess, not a peek
# at any specific outcome-model parameter) is the no-information default.
# Revised 2026-09-04 (see docs/build-log.md): the original weights ranked
# 168h above 24h, meaning a failed 72h attempt's SECOND try went to the
# offset FARTHEST from the middle checkpoint (96h away) before ever trying
# the offset genuinely closer to it (24h, only 48h away) - an internal
# contradiction with this comment's own "middle checkpoint favoured"
# rationale, not something derived from the sensitivity sweep's results.
# Reweighted by actual distance from the 72h checkpoint instead.
_OFFSET_WEIGHTS: dict[FailureCause, dict[int, float]] = {
    FailureCause.BANK_TECHNICAL: {24: 1.0, 72: 0.5, 168: 0.25},
    FailureCause.INSUFFICIENT_FUNDS: {24: 0.7, 72: 1.0, 168: 0.45},
}
_DEFAULT_OFFSET_WEIGHTS: dict[int, float] = {24: 0.8, 72: 1.0, 168: 0.6}

# A candidate inside the likely funding window scores higher than the same
# cause/offset heuristic alone would give it.
_FUNDING_WINDOW_BONUS = 1.5


class CandidateWindow(BaseModel):
    """One scored candidate retry time - kept even when rejected (PRD Sec 6.1)."""

    scheduled_at: datetime
    offset_label: str
    score: float
    compliant: bool
    rejected_reason: str | None = None


class AllocatorDecision(BaseModel):
    """Stage 5 output (PRD Sec 4)."""

    action: Action
    scheduled_at: datetime | None
    candidates: list[CandidateWindow]
    attempts_used: int
    attempts_remaining: int
    reason: str


def _fallback_funding_estimate() -> FundingWindowEstimate:
    """Stage 4 stub (PRD Sec 7 build step 4) - always the documented safe-spacing fallback."""
    return FundingWindowEstimate(likely_window=None, confidence=0.0, used_fallback=True)


def _score(recoverability: float, offset_weight: float, estimate: FundingWindowEstimate, scheduled_at: datetime) -> float:
    score = recoverability * offset_weight
    if not estimate.used_fallback and estimate.likely_window is not None:
        start, end = estimate.likely_window
        if start <= scheduled_at <= end:
            score *= _FUNDING_WINDOW_BONUS
    return round(score, 4)


def _score_candidates(
    cause: FailureCause, recoverability: float, failure_time: datetime, estimate: FundingWindowEstimate
) -> list[CandidateWindow]:
    weights = _OFFSET_WEIGHTS.get(cause, _DEFAULT_OFFSET_WEIGHTS)
    failure_time_ist = failure_time.astimezone(IST)
    candidates: list[CandidateWindow] = []
    for hours in _SAFE_SPACING_HOURS:
        naive = failure_time_ist + timedelta(hours=hours)
        label = f"{hours}h"
        if is_peak_window(naive):
            candidates.append(
                CandidateWindow(scheduled_at=naive, offset_label=label, score=0.0, compliant=False, rejected_reason="peak_window")
            )
            shifted = shift_out_of_peak(naive)
            score = _score(recoverability, weights[hours], estimate, shifted)
            candidates.append(CandidateWindow(scheduled_at=shifted, offset_label=f"{label}_shifted", score=score, compliant=True))
        else:
            score = _score(recoverability, weights[hours], estimate, naive)
            candidates.append(CandidateWindow(scheduled_at=naive, offset_label=label, score=score, compliant=True))
    return candidates


def allocate(
    cause: FailureCause,
    failure_time: datetime,
    attempts_used: int,
    funding_estimate: FundingWindowEstimate | None = None,
) -> AllocatorDecision:
    """Stage 5: decide notify / retry-at-T / stop (PRD Sec 4)."""
    if failure_time.tzinfo is None:
        raise ValueError("allocate requires a timezone-aware failure_time")

    prior = get_prior(cause)
    attempts_remaining = max(MAX_RETRY_ATTEMPTS - attempts_used, 0)

    if attempts_remaining <= 0:
        return AllocatorDecision(
            action="stop",
            scheduled_at=None,
            candidates=[],
            attempts_used=attempts_used,
            attempts_remaining=0,
            reason=f"retry budget exhausted ({attempts_used}/{MAX_RETRY_ATTEMPTS} attempts used)",
        )

    if prior.action_shape == "stop":
        return AllocatorDecision(
            action="stop",
            scheduled_at=None,
            candidates=[],
            attempts_used=attempts_used,
            attempts_remaining=attempts_remaining,
            reason=prior.rationale,
        )

    if prior.action_shape == "notify":
        return AllocatorDecision(
            action="notify",
            scheduled_at=None,
            candidates=[],
            attempts_used=attempts_used,
            attempts_remaining=attempts_remaining,
            reason=prior.rationale,
        )

    estimate = funding_estimate or _fallback_funding_estimate()
    candidates = _score_candidates(cause, prior.recoverability, failure_time, estimate)
    # Ranked, not just "the single best" - candidate generation doesn't
    # depend on attempts_used (it's always the same 3 safe-spacing offsets
    # from the original failure), so a later attempt must pick the next-best
    # *unused* window, not the same top-scoring one it (by definition)
    # already tried and that already failed. attempts_used indexes into the
    # ranking: attempt 1 gets the best window, attempt 2 the next-best, etc.
    compliant = sorted((c for c in candidates if c.compliant), key=lambda c: c.score, reverse=True)
    best = compliant[attempts_used]
    assert not is_peak_window(best.scheduled_at), "allocator must never choose a peak-window candidate"

    return AllocatorDecision(
        action="retry",
        scheduled_at=best.scheduled_at,
        candidates=candidates,
        attempts_used=attempts_used,
        attempts_remaining=attempts_remaining,
        reason=f"chose {best.offset_label} (score={best.score})",
    )


def run_allocation(
    cause: FailureCause,
    failure_time: datetime,
    attempts_used: int,
    funding_estimate: FundingWindowEstimate | None = None,
) -> tuple[AllocatorDecision, StageTrace]:
    """Stage 5 entry point: allocate and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"cause={cause.value} attempts_used={attempts_used}"

    def _work() -> tuple[AllocatorDecision, str]:
        decision = allocate(cause, failure_time, attempts_used, funding_estimate)
        return decision, f"action={decision.action} scheduled_at={decision.scheduled_at}"

    return run_stage("allocate", input_summary, _work)
