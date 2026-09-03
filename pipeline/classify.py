"""Stage 2 - deterministic cause classification (PRD Sec 4).

Maps the raw Razorpay error object to a FailureCause via lookup table. Never
an LLM call - this is the project's explicit "AI Judgment" answer, see
CLAUDE.md. The only model call in this codebase is Stage 7 (explain.py), and
it never touches this decision.
"""

from __future__ import annotations

from pydantic import BaseModel

from pipeline.models import FailureCause, RazorpayError, StageTrace, run_stage

# reason -> cause. insufficient_funds, bank_technical_error,
# gateway_technical_error, payment_timed_out, payment_declined, credit_failed
# and authentication_failed are documented Razorpay payment-error reasons
# (razorpay.com/docs/errors/payments/upi/, /docs/errors/payments/list/).
#
# Razorpay does not publish a dedicated `reason` for mandate revoked/expired
# or amount-exceeds-mandate in that list - those surface via the recurring
# token's lifecycle status (cancelled/paused/expired), not the charge error
# object. token_cancelled/token_expired/amount_exceeds_mandate below are
# provisional and must be checked against real fixtures once Sec 7 build
# step 3 (fixture capture) runs.
_REASON_TO_CAUSE: dict[str, FailureCause] = {
    "insufficient_funds": FailureCause.INSUFFICIENT_FUNDS,
    "bank_technical_error": FailureCause.BANK_TECHNICAL,
    "gateway_technical_error": FailureCause.BANK_TECHNICAL,
    "payment_timed_out": FailureCause.BANK_TECHNICAL,
    "payment_declined": FailureCause.BANK_TECHNICAL,
    "credit_failed": FailureCause.BANK_TECHNICAL,
    "authentication_failed": FailureCause.AFA_REQUIRED,
    "token_cancelled": FailureCause.MANDATE_REVOKED,
    "mandate_cancelled": FailureCause.MANDATE_REVOKED,
    "token_expired": FailureCause.MANDATE_EXPIRED,
    "mandate_expired": FailureCause.MANDATE_EXPIRED,
    "amount_exceeds_mandate": FailureCause.AMOUNT_EXCEEDS_MANDATE,
    "amount_limit_breached": FailureCause.AMOUNT_EXCEEDS_MANDATE,
}

# Fallback: keyword in `description`, checked only when `reason` has no exact
# match above. Still deterministic string matching, not inference.
# ponytail: substring match over a small list, not a scoring/NLP model - good
# enough for cases where `reason` is missing; revisit if real fixtures show
# descriptions that collide across causes.
_DESCRIPTION_KEYWORDS: tuple[tuple[str, FailureCause], ...] = (
    ("sufficient fund", FailureCause.INSUFFICIENT_FUNDS),
    ("mandate has been cancelled", FailureCause.MANDATE_REVOKED),
    ("mandate cancelled", FailureCause.MANDATE_REVOKED),
    ("revoked", FailureCause.MANDATE_REVOKED),
    ("mandate has expired", FailureCause.MANDATE_EXPIRED),
    ("mandate expired", FailureCause.MANDATE_EXPIRED),
    ("exceeds", FailureCause.AMOUNT_EXCEEDS_MANDATE),
    ("additional factor", FailureCause.AFA_REQUIRED),
    ("authentication", FailureCause.AFA_REQUIRED),
    ("technical", FailureCause.BANK_TECHNICAL),
    ("downtime", FailureCause.BANK_TECHNICAL),
)


class ClassificationResult(BaseModel):
    """Stage 2 output: the cause, a rule-based confidence, and what matched."""

    cause: FailureCause
    confidence: float
    matched_on: str


def classify_cause(error: RazorpayError) -> ClassificationResult:
    """Deterministically map a Razorpay error object to a FailureCause (PRD Sec 4, Stage 2)."""
    reason = (error.reason or "").strip().lower()
    if reason in _REASON_TO_CAUSE:
        return ClassificationResult(
            cause=_REASON_TO_CAUSE[reason], confidence=1.0, matched_on=f"reason:{reason}"
        )

    description = (error.description or "").lower()
    for keyword, cause in _DESCRIPTION_KEYWORDS:
        if keyword in description:
            return ClassificationResult(
                cause=cause, confidence=0.6, matched_on=f"description_keyword:{keyword}"
            )

    return ClassificationResult(cause=FailureCause.UNKNOWN, confidence=0.0, matched_on="no_match")


def run_classification(error: RazorpayError) -> tuple[ClassificationResult, StageTrace]:
    """Stage 2 entry point: classify and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"reason={error.reason!r} code={error.code!r}"

    def _work() -> tuple[ClassificationResult, str]:
        result = classify_cause(error)
        return result, f"cause={result.cause.value} confidence={result.confidence}"

    return run_stage("classify", input_summary, _work)
