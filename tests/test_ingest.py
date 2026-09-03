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


def test_run_ingestion_returns_stage_trace() -> None:
    event, trace = run_ingestion(_VALID_RAW)
    assert event.payment_id == "pay_TEST001"
    assert trace.stage == "ingest"
    assert trace.skipped is False
