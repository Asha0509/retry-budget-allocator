"""Unit tests for the pipeline orchestrator (PRD Sec 4, Sec 6.1)."""

from pipeline.ingest import ingest
from pipeline.run import run_pipeline

_RAW_INSUFFICIENT_FUNDS = {
    "payment_id": "pay_A",
    "token_id": "token_A",
    "customer_id": "cust_A",
    "amount": 50000,
    "error": {"code": "BAD_REQUEST_ERROR", "reason": "insufficient_funds"},
    "attempts_used": 0,
    "failure_time": "2026-09-03T08:00:00+05:30",
}

_RAW_MANDATE_REVOKED = {
    "payment_id": "pay_B",
    "token_id": "token_B",
    "customer_id": "cust_B",
    "amount": 20000,
    "error": {"code": "GATEWAY_ERROR", "reason": "token_cancelled"},
    "attempts_used": 0,
    "failure_time": "2026-09-03T08:00:00+05:30",
}

_RAW_INSUFFICIENT_FUNDS_WITH_HISTORY = {
    **_RAW_INSUFFICIENT_FUNDS,
    "payment_id": "pay_C",
    "prior_debit_dates": ["2026-06-05T08:00:00+05:30", "2026-07-05T08:00:00+05:30", "2026-08-06T08:00:00+05:30"],
}


def test_run_pipeline_produces_five_stage_traces_in_order() -> None:
    event = ingest(_RAW_INSUFFICIENT_FUNDS)
    decision, traces = run_pipeline(event)
    assert [t.stage for t in traces] == ["classify", "priors", "funding_window", "allocate", "decision"]
    assert decision.action == "retry"


def test_funding_window_actually_runs_for_insufficient_funds_without_history() -> None:
    # No prior_debit_dates -> genuinely runs Stage 4, which correctly falls
    # back to safe spacing rather than being skipped outright.
    event = ingest(_RAW_INSUFFICIENT_FUNDS)
    _, traces = run_pipeline(event)
    funding_trace = next(t for t in traces if t.stage == "funding_window")
    assert funding_trace.skipped is False
    assert "used_fallback=True" in funding_trace.output_summary


def test_funding_window_uses_real_history_when_available() -> None:
    event = ingest(_RAW_INSUFFICIENT_FUNDS_WITH_HISTORY)
    decision, traces = run_pipeline(event)
    funding_trace = next(t for t in traces if t.stage == "funding_window")
    assert funding_trace.skipped is False
    assert decision.action == "retry"


def test_funding_window_marked_not_applicable_for_other_causes() -> None:
    event = ingest(_RAW_MANDATE_REVOKED)
    decision, traces = run_pipeline(event)
    funding_trace = next(t for t in traces if t.stage == "funding_window")
    assert funding_trace.skipped is True
    assert "only applies to insufficient_funds" in funding_trace.skip_reason
    assert decision.action == "stop"


def test_custom_explain_plain_flows_through_the_whole_pipeline() -> None:
    event = ingest(_RAW_INSUFFICIENT_FUNDS)
    decision, _ = run_pipeline(event, explain_plain=lambda cause, action: f"custom {cause.value} {action}")
    assert decision.reasoning_plain == "custom insufficient_funds retry"
