"""Unit tests for Stage 6 decision assembly (PRD Sec 4)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from pipeline.allocator import allocate
from pipeline.classify import classify_cause
from pipeline.decision import run_decision
from pipeline.models import RazorpayError
from pipeline.priors import get_prior

IST = ZoneInfo("Asia/Kolkata")


def test_assemble_decision_carries_raw_error_and_all_candidates() -> None:
    error = RazorpayError(code="BAD_REQUEST_ERROR", reason="insufficient_funds", description="not enough funds", metadata={"upi_error_code": "Z9"})
    classification = classify_cause(error)
    prior = get_prior(classification.cause)
    allocation = allocate(classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0)

    decision, trace = run_decision("pay_1", "token_1", 50000, error, classification, prior, allocation)

    assert trace.stage == "decision"
    assert decision.raw_error.model_dump()["metadata"] == {"upi_error_code": "Z9"}
    assert decision.raw_error.reason == "insufficient_funds"
    assert len(decision.candidates) == len(allocation.candidates)
    assert decision.action == "retry"
    assert decision.recoverable is True
    assert decision.window_compliant is True
    assert decision.reasoning_plain != ""
    assert "insufficient_funds" in decision.reasoning_technical


def test_stop_decision_has_no_scheduled_time_and_is_window_compliant_by_definition() -> None:
    error = RazorpayError(reason="token_cancelled")
    classification = classify_cause(error)
    prior = get_prior(classification.cause)
    allocation = allocate(classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0)

    decision, _ = run_decision("pay_2", "token_2", 50000, error, classification, prior, allocation)

    assert decision.action == "stop"
    assert decision.scheduled_at is None
    assert decision.window_compliant is True
    assert decision.recoverable is False


def test_custom_explain_plain_is_used_when_provided() -> None:
    error = RazorpayError(reason="insufficient_funds")
    classification = classify_cause(error)
    prior = get_prior(classification.cause)
    allocation = allocate(classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0)

    decision, _ = run_decision(
        "pay_3", "token_3", 100, error, classification, prior, allocation, explain_plain=lambda cause, action: "custom text"
    )
    assert decision.reasoning_plain == "custom text"


def test_billing_cycle_successes_carried_from_allocation_onto_the_decision_record() -> None:
    error = RazorpayError(reason="bank_technical")
    classification = classify_cause(error)
    prior = get_prior(classification.cause)
    allocation = allocate(
        classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0, billing_cycle_successes=1
    )

    decision, _ = run_decision("pay_4", "token_4", 50000, error, classification, prior, allocation)

    assert decision.billing_cycle_successes == 1
    assert decision.action == "stop"


def test_a_prior_success_this_cycle_gets_an_accurate_plain_sentence_not_the_generic_stop_one() -> None:
    # Regression test for docs/build-log.md (2026-09-15): the generic "stop"
    # template says the customer needs a new mandate, which is wrong here -
    # nothing about the mandate failed, a debit already succeeded.
    error = RazorpayError(reason="bank_technical_error")
    classification = classify_cause(error)
    prior = get_prior(classification.cause)
    allocation = allocate(
        classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0, billing_cycle_successes=1
    )

    decision, _ = run_decision("pay_5", "token_5", 50000, error, classification, prior, allocation)

    assert "mandate" not in decision.reasoning_plain.lower()
    assert "billing cycle" in decision.reasoning_plain.lower()

    # Even a custom explain_plain hook doesn't override this - it's a
    # compliance fact, not a stylistic choice.
    decision_custom, _ = run_decision(
        "pay_6", "token_6", 50000, error, classification, prior, allocation, explain_plain=lambda cause, action: "custom text"
    )
    assert decision_custom.reasoning_plain != "custom text"
