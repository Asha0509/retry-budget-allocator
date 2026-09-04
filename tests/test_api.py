"""Unit tests for the live-simulator API (Gap 3, PRD Sec 6.2 opt-in live mode).

Stubs Stage 7 (LLM explanation) the same way tests/test_harness.py does -
network-dependent, rate-limited, no place in an automated test suite.
pipeline/explain.py's own mocked tests already cover that logic in depth.
"""

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from pipeline.explain import ExplanationResult
from pipeline.models import StageTrace


def _stub_run_explanation(decision):
    result = ExplanationResult(
        reasoning_plain="stub reasoning", notification_copy_en="stub en", notification_copy_hinglish="stub hi", generated_by="llm"
    )
    trace = StageTrace(stage="explain", input_summary="stub", output_summary="stub", elapsed_ms=1.0)
    return result, trace


@pytest.fixture(autouse=True)
def _stub_explanation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(api_main, "run_explanation", _stub_run_explanation)


@pytest.fixture
def client():
    return TestClient(api_main.app)


def test_list_personas_returns_all_four(client) -> None:
    resp = client.get("/api/personas")
    assert resp.status_code == 200
    keys = {p["key"] for p in resp.json()}
    assert keys == {"priya", "rahul", "ananya", "karan"}


def test_simulate_priya_persona_retries(client) -> None:
    resp = client.post("/api/simulate", json={"persona": "priya"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocator_decision"]["cause"] == "insufficient_funds"
    assert body["allocator_decision"]["action"] == "retry"
    assert body["explanation"]["generated_by"] == "llm"
    stages = [t["stage"] for t in body["allocator_stage_traces"]]
    assert stages == ["ingest", "classify", "priors", "funding_window", "allocate", "decision", "explain"]


def test_simulate_rahul_persona_stops_and_disagrees_with_baseline(client) -> None:
    resp = client.post("/api/simulate", json={"persona": "rahul"})
    body = resp.json()
    assert body["allocator_decision"]["cause"] == "mandate_expired"
    assert body["allocator_decision"]["action"] == "stop"
    # baseline is cause-agnostic and always retries while budget remains
    assert body["baseline_decision"]["action"] == "retry"
    assert body["decisions_differ"] is True


def test_simulate_karan_persona_notifies_not_retries_or_stops(client) -> None:
    resp = client.post("/api/simulate", json={"persona": "karan"})
    body = resp.json()
    assert body["allocator_decision"]["cause"] == "afa_required"
    assert body["allocator_decision"]["action"] == "notify"
    assert body["baseline_decision"]["action"] == "retry"
    assert body["decisions_differ"] is True


def test_simulate_unknown_persona_returns_404(client) -> None:
    resp = client.post("/api/simulate", json={"persona": "nonexistent"})
    assert resp.status_code == 404


def test_simulate_custom_cause_dropdown(client) -> None:
    resp = client.post("/api/simulate", json={"cause": "bank_technical", "amount": 50000})
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocator_decision"]["cause"] == "bank_technical"
    assert body["amount"] == 50000


def test_simulate_custom_raw_error_paste(client) -> None:
    resp = client.post(
        "/api/simulate",
        json={"raw_error": {"code": "BAD_REQUEST_ERROR", "reason": "insufficient_funds", "description": "not enough funds"}},
    )
    assert resp.status_code == 200
    assert resp.json()["allocator_decision"]["cause"] == "insufficient_funds"


def test_simulate_unrecognized_raw_error_is_shown_honestly_as_unknown(client) -> None:
    # PRD Sec 4 Stage 2 / CLAUDE.md hard constraint: never force a confident
    # guess - a genuinely unrecognized payload must classify as unknown with
    # zero confidence, live, not just in a doc.
    resp = client.post(
        "/api/simulate",
        json={"raw_error": {"code": "SOMETHING_ELSE", "reason": "totally_unrecognized_reason_xyz", "description": "gibberish"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allocator_decision"]["cause"] == "unknown"
    assert body["allocator_decision"]["cause_confidence"] == 0.0


def test_simulate_requires_persona_cause_or_raw_error(client) -> None:
    resp = client.post("/api/simulate", json={})
    assert resp.status_code == 400


def test_simulate_invalid_cause_value_returns_400(client) -> None:
    resp = client.post("/api/simulate", json={"cause": "not_a_real_cause"})
    assert resp.status_code == 400


def test_simulate_rejects_nonpositive_amount(client) -> None:
    # A failed debit can't be for zero or negative money - a skeptical
    # reviewer trying to break the form should get a clean 422, not a
    # decision computed over nonsense.
    resp = client.post("/api/simulate", json={"cause": "insufficient_funds", "amount": -500})
    assert resp.status_code == 422
    resp = client.post("/api/simulate", json={"cause": "insufficient_funds", "amount": 0})
    assert resp.status_code == 422


def test_simulate_rejects_malformed_raw_error_type(client) -> None:
    resp = client.post("/api/simulate", json={"raw_error": "not a dict"})
    assert resp.status_code == 422


def test_simulate_rejects_out_of_range_attempts_used(client) -> None:
    resp = client.post("/api/simulate", json={"cause": "bank_technical", "attempts_used": 4})
    assert resp.status_code == 422


def test_degraded_explanation_is_visible_in_the_response(client, monkeypatch: pytest.MonkeyPatch) -> None:
    def _failing_explanation(decision):
        result = ExplanationResult(
            reasoning_plain="fallback text", notification_copy_en="fallback en", notification_copy_hinglish="fallback hi",
            generated_by="template_fallback",
        )
        trace = StageTrace(stage="explain", input_summary="stub", output_summary="stub", elapsed_ms=1.0)
        return result, trace

    monkeypatch.setattr(api_main, "run_explanation", _failing_explanation)
    resp = client.post("/api/simulate", json={"persona": "ananya"})
    assert resp.json()["explanation"]["generated_by"] == "template_fallback"
