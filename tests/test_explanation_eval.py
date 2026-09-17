"""Tests for the Stage 7 faithfulness eval (PRD Sec 4 Stage 7, Sec 6.4).

Each check must pass a faithful explanation and catch the specific failure it
exists for - otherwise a 100% pass rate would mean nothing. No network.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from eval.explanation_eval import (
    CHECK_NAMES,
    check_action,
    check_amounts,
    check_customer_jargon,
    check_hinglish,
    check_internal_leak,
    check_jargon_explained,
    check_sms_length,
    check_times,
    evaluate_one,
    rows_from_llm,
    summarise,
)
from pipeline.allocator import allocate
from pipeline.classify import classify_cause
from pipeline.decision import RecoveryDecision, run_decision
from pipeline.explain import ExplanationResult, _fallback_explanation
from pipeline.models import RazorpayError
from pipeline.priors import get_prior

IST = ZoneInfo("Asia/Kolkata")


def _decision(reason: str, billing_cycle_successes: int = 0) -> RecoveryDecision:
    error = RazorpayError(reason=reason)
    classification = classify_cause(error)
    allocation = allocate(
        classification.cause, datetime(2026, 9, 3, 8, 0, tzinfo=IST), attempts_used=0,
        billing_cycle_successes=billing_cycle_successes,
    )
    decision, _ = run_decision("pay_1", "token_1", 50000, error, classification, get_prior(classification.cause), allocation)
    return decision


def _exp(plain: str = "We'll try this payment again later.", en: str = "We'll retry your payment soon - no action needed.",
         hi: str = "Aapka payment phir se try hoga - abhi kuch karne ki zaroorat nahi hai.") -> ExplanationResult:
    return ExplanationResult(reasoning_plain=plain, notification_copy_en=en, notification_copy_hinglish=hi, generated_by="llm")


@pytest.fixture
def retry() -> RecoveryDecision:
    d = _decision("insufficient_funds")
    assert d.action == "retry"
    return d


@pytest.fixture
def stop() -> RecoveryDecision:
    d = _decision("mandate_cancelled")
    assert d.action == "stop"
    return d


@pytest.mark.parametrize("reason", ["insufficient_funds", "bank_technical_error", "mandate_cancelled", "mandate_expired", "authentication_failed", "something_new"])
def test_every_template_explanation_passes_every_check(reason: str) -> None:
    decision = _decision(reason)
    row = evaluate_one(decision, _fallback_explanation(decision))
    assert row["passed"], row["failed_checks"]


def test_already_paid_this_cycle_template_passes() -> None:
    decision = _decision("bank_technical_error", billing_cycle_successes=1)
    assert evaluate_one(decision, _fallback_explanation(decision))["passed"]


def test_stop_that_promises_a_retry_is_caught(stop: RecoveryDecision) -> None:
    bad = _exp(plain="We've stopped.", en="Don't worry, we'll retry your payment tomorrow.")
    assert not check_action(stop, bad).passed


def test_stop_without_asking_the_customer_to_act_is_caught(stop: RecoveryDecision) -> None:
    bad = _exp(plain="We've stopped.", en="Your payment did not go through.", hi="Aapka payment nahi hua hai.")
    assert not check_action(stop, bad).passed


def test_retry_that_never_says_it_will_try_again_is_caught(retry: RecoveryDecision) -> None:
    bad = _exp(plain="Payment failed.", en="Your payment failed.")
    assert not check_action(retry, bad).passed
    assert check_action(retry, _exp()).passed


def test_invented_amount_is_caught_and_the_real_one_passes(retry: RecoveryDecision) -> None:
    assert not check_amounts(retry, _exp(en="We'll retry your ₹5,000 payment soon.")).passed
    assert check_amounts(retry, _exp(en="We'll retry your ₹500 payment soon.")).passed
    assert check_amounts(retry, _exp(en="We'll retry your Rs. 500.00 payment soon.")).passed


def test_wrong_time_and_date_are_caught_and_the_scheduled_ones_pass(retry: RecoveryDecision) -> None:
    when = retry.scheduled_at.astimezone(IST)
    right = f"We'll retry on {when.day} {when:%B} at {when:%H:%M}."
    assert check_times(retry, _exp(en=right)).passed
    assert not check_times(retry, _exp(en=f"We'll retry on {when.day} {when:%B} at 23:59.")).passed
    assert not check_times(retry, _exp(en=f"We'll retry on {(when.day % 28) + 1} {when:%B}.")).passed


def test_a_time_with_nothing_scheduled_is_caught(stop: RecoveryDecision) -> None:
    assert not check_times(stop, _exp(en="Please set it up again before 5 pm.")).passed


def test_customer_jargon_is_caught(retry: RecoveryDecision) -> None:
    for word in ("Your mandate failed.", "NPCI rules apply.", "Error BAD_REQUEST_ERROR.", "Cause: insufficient_funds."):
        assert not check_customer_jargon(retry, _exp(en=word)).passed


def test_jargon_in_brackets_after_plain_words_is_allowed(stop: RecoveryDecision) -> None:
    assert check_jargon_explained(stop, _exp(plain="They need to set up automatic payments again (a new mandate).")).passed
    assert not check_jargon_explained(stop, _exp(plain="They need a new mandate.")).passed


def test_internal_details_are_caught(retry: RecoveryDecision) -> None:
    assert not check_internal_leak(retry, _exp(plain="Chose 24h_shifted.")).passed
    assert not check_internal_leak(retry, _exp(en="Ref pay_1: retrying soon.")).passed
    assert not check_internal_leak(retry, _exp(plain="Score was high.")).passed


def test_long_sms_is_caught(retry: RecoveryDecision) -> None:
    assert not check_sms_length(retry, _exp(en="We'll retry. " * 20)).passed


def test_hinglish_must_not_be_english_again(retry: RecoveryDecision) -> None:
    same = _exp(en="We'll retry soon.", hi="We'll retry soon.")
    assert not check_hinglish(retry, same).passed
    assert not check_hinglish(retry, _exp(hi="Payment retry soon.")).passed
    assert check_hinglish(retry, _exp()).passed


def test_summary_counts_failures_per_check(retry: RecoveryDecision) -> None:
    rows = [evaluate_one(retry, _exp()), evaluate_one(retry, _exp(en="We'll retry your ₹9,999 payment."))]
    s = summarise(rows)
    assert s["n"] == 2 and s["pass_rate"] == 0.5
    assert s["per_check"]["amounts_match"]["failed"] == 1
    assert set(s["per_check"]) == set(CHECK_NAMES)


def test_llm_source_refuses_without_the_live_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE_LLM", raising=False)
    with pytest.raises(RuntimeError, match="LIVE_LLM=1"):
        rows_from_llm({"payments": []})
