"""Unit tests for Stage 1 ingestion (PRD Sec 4)."""

import pytest
from pydantic import ValidationError

from pipeline.ingest import ingest, run_ingestion

_VALID_RAW = {
    "payment_id": "pay_TEST001",
    "token_id": "token_TEST001",
    "customer_id": "cust_TEST001",
    "amount": 50000,
    "error": {"code": "BAD_REQUEST_ERROR", "reason": "insufficient_funds"},
    "attempts_used": 0,
    "failure_time": "2026-09-03T08:00:00+05:30",
}


def test_ingest_parses_a_valid_event() -> None:
    event = ingest(_VALID_RAW)
    assert event.payment_id == "pay_TEST001"
    assert event.error.reason == "insufficient_funds"
    assert event.currency == "INR"
    assert event.billing_cycle_successes == 0


def test_ingest_rejects_malformed_event() -> None:
    bad = dict(_VALID_RAW)
    del bad["amount"]
    with pytest.raises(ValidationError):
        ingest(bad)


@pytest.mark.parametrize("bad_amount", [0, -1, -50000])
def test_ingest_rejects_non_positive_amount(bad_amount: int) -> None:
    # Absent/malformed money data must fail at Stage 1, not flow downstream
    # into amount_recovered arithmetic as a silently negative or zero figure.
    bad = dict(_VALID_RAW, amount=bad_amount)
    with pytest.raises(ValidationError):
        ingest(bad)


@pytest.mark.parametrize("bad_attempts_used", [-1, -5, 4, 100])
def test_ingest_rejects_out_of_range_attempts_used(bad_attempts_used: int) -> None:
    # Regression test (docs/build-log.md): this field used to have no bound
    # at the ingestion boundary at all, despite this module's own docstring
    # claiming malformed events fail loudly here.
    bad = dict(_VALID_RAW, attempts_used=bad_attempts_used)
    with pytest.raises(ValidationError):
        ingest(bad)


def test_ingest_accepts_attempts_used_at_cap_boundary() -> None:
    # 3 is valid at ingestion (budget fully spent, not an invalid value) -
    # the allocator decides "stop" for it, ingestion shouldn't reject it.
    event = ingest(dict(_VALID_RAW, attempts_used=3))
    assert event.attempts_used == 3


def test_run_ingestion_returns_stage_trace() -> None:
    event, trace = run_ingestion(_VALID_RAW)
    assert event.payment_id == "pay_TEST001"
    assert trace.stage == "ingest"
    assert trace.skipped is False
