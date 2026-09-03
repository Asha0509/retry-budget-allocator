"""Unit tests for Stage 2 cause classification (PRD Sec 4, Sec 7 build step 1)."""

import pytest

from pipeline.classify import classify_cause, run_classification
from pipeline.models import FailureCause, RazorpayError

REASON_CASES = [
    ("insufficient_funds", FailureCause.INSUFFICIENT_FUNDS),
    ("bank_technical_error", FailureCause.BANK_TECHNICAL),
    ("gateway_technical_error", FailureCause.BANK_TECHNICAL),
    ("payment_timed_out", FailureCause.BANK_TECHNICAL),
    ("payment_declined", FailureCause.BANK_TECHNICAL),
    ("credit_failed", FailureCause.BANK_TECHNICAL),
    ("authentication_failed", FailureCause.AFA_REQUIRED),
    ("token_cancelled", FailureCause.MANDATE_REVOKED),
    ("mandate_cancelled", FailureCause.MANDATE_REVOKED),
    ("token_expired", FailureCause.MANDATE_EXPIRED),
    ("mandate_expired", FailureCause.MANDATE_EXPIRED),
    ("amount_exceeds_mandate", FailureCause.AMOUNT_EXCEEDS_MANDATE),
    ("amount_limit_breached", FailureCause.AMOUNT_EXCEEDS_MANDATE),
]


@pytest.mark.parametrize("reason,expected_cause", REASON_CASES)
def test_reason_lookup_covers_every_cause(reason: str, expected_cause: FailureCause) -> None:
    error = RazorpayError(code="BAD_REQUEST_ERROR", reason=reason, description="", source="bank", step="processing")
    result = classify_cause(error)
    assert result.cause == expected_cause
    assert result.confidence == 1.0
    assert result.matched_on == f"reason:{reason}"


def test_all_seven_causes_are_reachable() -> None:
    reachable = {cause for _, cause in REASON_CASES} | {FailureCause.UNKNOWN}
    assert reachable == set(FailureCause)


def test_reason_match_is_case_and_whitespace_insensitive() -> None:
    error = RazorpayError(reason="  Insufficient_Funds  ")
    result = classify_cause(error)
    assert result.cause == FailureCause.INSUFFICIENT_FUNDS


def test_real_documented_upi_insufficient_funds_payload() -> None:
    """Payload shape from razorpay.com/docs/errors/payments/upi/."""
    error = RazorpayError(
        code="BAD_REQUEST_ERROR",
        description="Customer's bank account did not have enough funds to complete the transaction",
        source="customer",
        step="payment_authorization",
        reason="insufficient_funds",
    )
    result = classify_cause(error)
    assert result.cause == FailureCause.INSUFFICIENT_FUNDS
    assert result.confidence == 1.0


def test_description_keyword_fallback_when_reason_unrecognized() -> None:
    error = RazorpayError(
        code="GATEWAY_ERROR",
        description="The customer's mandate has been cancelled by the bank",
        reason="unmapped_bank_code_47",
    )
    result = classify_cause(error)
    assert result.cause == FailureCause.MANDATE_REVOKED
    assert result.confidence == 0.6
    assert result.matched_on.startswith("description_keyword:")


def test_no_reason_and_no_description_match_is_unknown() -> None:
    error = RazorpayError(code="GATEWAY_ERROR", description="Something unexpected happened", reason=None)
    result = classify_cause(error)
    assert result.cause == FailureCause.UNKNOWN
    assert result.confidence == 0.0
    assert result.matched_on == "no_match"


def test_raw_payload_fields_are_preserved_not_discarded() -> None:
    """Hard constraint: raw error payload carried through, never dropped after classification."""
    error = RazorpayError(
        code="BAD_REQUEST_ERROR",
        reason="insufficient_funds",
        metadata={"upi_error_code": "Z9"},
        field="vpa",
    )
    classify_cause(error)  # classification must not mutate the payload
    dumped = error.model_dump()
    assert dumped["metadata"] == {"upi_error_code": "Z9"}
    assert dumped["field"] == "vpa"
    assert dumped["reason"] == "insufficient_funds"


def test_run_classification_returns_stage_trace() -> None:
    error = RazorpayError(reason="bank_technical_error")
    result, trace = run_classification(error)
    assert result.cause == FailureCause.BANK_TECHNICAL
    assert trace.stage == "classify"
    assert trace.skipped is False
    assert trace.elapsed_ms >= 0
    assert "cause=bank_technical" in trace.output_summary
    assert "reason='bank_technical_error'" in trace.input_summary
