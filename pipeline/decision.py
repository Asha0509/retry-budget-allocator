"""Stage 6 - decision record (PRD Sec 4).

Assembles the outputs of every prior stage into one RecoveryDecision. Two
hard constraints enforced here: the raw error payload is carried through
(never discarded after classification), and every scored candidate window is
kept (never only the winner).

`reasoning_plain` defaults to a deterministic template - Stage 7's LLM layer
(build step 10) is off the critical path by design, so decision assembly
must work correctly with or without it. `explain_plain` is the seam step 10
plugs a real call into, same pattern as the allocator's funding_estimate.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel

from pipeline.allocator import AllocatorDecision, CandidateWindow
from pipeline.classify import ClassificationResult
from pipeline.compliance import is_peak_window
from pipeline.models import Action, FailureCause, RazorpayError, StageTrace, run_stage
from pipeline.priors import RecoverabilityPrior

_ACTION_PLAIN_TEMPLATES: dict[Action, str] = {
    "retry": "We'll try this payment again at a compliant time when it's more likely to succeed.",
    "notify": "We're letting the customer know so they can fix this themselves - retrying automatically won't work here.",
    "stop": "We've stopped trying - this payment cannot succeed without the customer setting up a new mandate.",
}

# The generic "stop" template above is wrong for this one specific stop
# reason - a prior success this cycle has nothing to do with the mandate
# needing to be redone (PRD Sec 2, docs/build-log.md 2026-09-15). Checked
# ahead of the per-action table in assemble_decision() below.
_ALREADY_SUCCEEDED_THIS_CYCLE_PLAIN = (
    "We've stopped trying - a payment already went through successfully this billing cycle, "
    "so trying again isn't needed and isn't allowed."
)


def _template_reasoning_plain(cause: FailureCause, action: Action) -> str:
    """Deterministic fallback used until Stage 7 (build step 10) generates a real one."""
    return _ACTION_PLAIN_TEMPLATES[action]


class RecoveryDecision(BaseModel):
    """Stage 6 output (PRD Sec 4)."""

    payment_id: str
    token_id: str
    amount: int
    cause: FailureCause
    cause_confidence: float
    recoverable: bool
    action: Action
    scheduled_at: datetime | None
    window_compliant: bool
    attempts_used: int
    attempts_remaining: int
    billing_cycle_successes: int
    reasoning_plain: str
    reasoning_technical: str
    raw_error: RazorpayError
    candidates: list[CandidateWindow]


def assemble_decision(
    payment_id: str,
    token_id: str,
    amount: int,
    raw_error: RazorpayError,
    classification: ClassificationResult,
    prior: RecoverabilityPrior,
    allocation: AllocatorDecision,
    explain_plain: Callable[[FailureCause, Action], str] = _template_reasoning_plain,
) -> RecoveryDecision:
    """Stage 6: combine every prior stage's output into one decision record (PRD Sec 4)."""
    window_compliant = allocation.scheduled_at is None or not is_peak_window(allocation.scheduled_at)
    reasoning_technical = (
        f"cause={classification.cause.value} (confidence={classification.confidence}, "
        f"matched_on={classification.matched_on}); recoverability={prior.recoverability}; "
        f"action={allocation.action}; {allocation.reason}"
    )
    return RecoveryDecision(
        payment_id=payment_id,
        token_id=token_id,
        amount=amount,
        cause=classification.cause,
        cause_confidence=classification.confidence,
        recoverable=prior.recoverability > 0.0,
        action=allocation.action,
        scheduled_at=allocation.scheduled_at,
        window_compliant=window_compliant,
        attempts_used=allocation.attempts_used,
        attempts_remaining=allocation.attempts_remaining,
        billing_cycle_successes=allocation.billing_cycle_successes,
        # Bypasses a custom explain_plain hook for this one case (allocation.
        # billing_cycle_successes>=1 always means action="stop", by
        # construction in allocate()/baseline_decide()) - this is a
        # compliance-audit fact, not a stylistic explanation choice, so it
        # stays correct the same way the peak-window assert does rather
        # than being left to a pluggable, potentially-wrong template.
        reasoning_plain=(
            _ALREADY_SUCCEEDED_THIS_CYCLE_PLAIN
            if allocation.billing_cycle_successes >= 1
            else explain_plain(classification.cause, allocation.action)
        ),
        reasoning_technical=reasoning_technical,
        raw_error=raw_error,
        candidates=allocation.candidates,
    )


def run_decision(
    payment_id: str,
    token_id: str,
    amount: int,
    raw_error: RazorpayError,
    classification: ClassificationResult,
    prior: RecoverabilityPrior,
    allocation: AllocatorDecision,
    explain_plain: Callable[[FailureCause, Action], str] = _template_reasoning_plain,
) -> tuple[RecoveryDecision, StageTrace]:
    """Stage 6 entry point: assemble the decision and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"payment_id={payment_id!r} cause={classification.cause.value}"

    def _work() -> tuple[RecoveryDecision, str]:
        decision = assemble_decision(payment_id, token_id, amount, raw_error, classification, prior, allocation, explain_plain)
        return decision, f"action={decision.action} recoverable={decision.recoverable}"

    return run_stage("decision", input_summary, _work)
