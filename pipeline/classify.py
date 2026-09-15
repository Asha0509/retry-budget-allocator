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
# gateway_technical_error, payment_timed_out, payment_declined, credit_failed,
# authentication_failed, payment_collect_request_expired,
# vpa_resolution_failed, and reqauth_mandate_not_acknowledged are documented
# Razorpay payment-error reasons (razorpay.com/docs/errors/payments/upi/,
# /docs/errors/payments/list/ - full audit against both pages, 2026-09-15,
# Part C4).
#
# Razorpay does not publish a dedicated `reason` for mandate revoked/expired
# or amount-exceeds-mandate in that list - those surface via the recurring
# token's lifecycle status (cancelled/paused/expired), not the charge error
# object. token_cancelled/token_expired/amount_exceeds_mandate below are
# provisional and must be checked against real fixtures once Sec 7 build
# step 3 (fixture capture) runs.
#
# Deliberately left OUT of this table, and out of the FailureCause taxonomy
# entirely (2026-09-15 audit) - not a coverage gap, a scope boundary:
#   - mandate_creation_declined/expired/failed/timeout - these are mandate
#     REGISTRATION failures. This classifier handles why an EXISTING
#     mandate's recurring CHARGE failed; there is no token yet to schedule
#     a retry against, and the NPCI 3-attempt cap this whole system is
#     built around doesn't apply to mandate creation at all. A different
#     problem, not a code gap.
#   - recurring_payment_not_enabled - Source: business. A merchant account
#     configuration error, not a customer payment failure. Out of scope
#     for the same reason "the server is down" would be.
#
# Deliberately left unmapped, WITHIN scope, and falls through to UNKNOWN ->
# notify (2026-09-15 audit) - a real code exists but none of the 7 causes
# fit it honestly, and forcing one would give priors.py a wrong
# recoverability/action_shape rather than the correct conservative default:
#   - invalid_vpa - the customer isn't a valid UPI user / hasn't completed
#     VPA registration. Not a fund, mandate, or auth-timing issue - it's a
#     payment-method eligibility problem none of the 7 causes describes.
#   - payment_cancelled - the customer actively backed out. Different
#     intent from a technical failure; blind-retrying a deliberate
#     cancellation isn't obviously safe or useful, and there's no
#     "customer changed their mind" cause. notify is the honest default.
#   - funds_blocked_by_mandate - funds exist but are reserved by a
#     DIFFERENT mandate. Needs the customer to release that mandate or use
#     another account - closer to needing customer action than to plain
#     insufficient_funds, but there's no clean existing bucket for it.
_REASON_TO_CAUSE: dict[str, FailureCause] = {
    "insufficient_funds": FailureCause.INSUFFICIENT_FUNDS,
    "bank_technical_error": FailureCause.BANK_TECHNICAL,
    "gateway_technical_error": FailureCause.BANK_TECHNICAL,
    "payment_timed_out": FailureCause.BANK_TECHNICAL,
    "payment_declined": FailureCause.BANK_TECHNICAL,
    "credit_failed": FailureCause.BANK_TECHNICAL,
    # Identical "10-minute time limit" description to payment_timed_out
    # (razorpay.com/docs/errors/payments/upi/) - same bucket, same reason.
    "payment_collect_request_expired": FailureCause.BANK_TECHNICAL,
    # "Escalate to technical support" - same infra-failure framing as
    # gateway_technical_error, already in this bucket.
    "vpa_resolution_failed": FailureCause.BANK_TECHNICAL,
    "authentication_failed": FailureCause.AFA_REQUIRED,
    # "Customer needs to acknowledge the mandate" - can't be supplied by a
    # silent retry, same shape as authentication_failed.
    "reqauth_mandate_not_acknowledged": FailureCause.AFA_REQUIRED,
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
