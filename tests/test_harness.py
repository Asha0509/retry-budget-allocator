"""Unit tests for the batch runner + eval harness (PRD Sec 5, Sec 7 build step 7).

Redirects eval.harness's output directories into pytest's tmp_path for every
test here - run_batch writes real files, and tests must never pollute the
actual eval/results/, data/runs/, or logs/ directories the real batch run
(and the committed sample log) live in. Also stubs out Stage 7 (LLM
explanation) - run_batch calls the real, network-dependent, rate-limited
free-tier provider by design (PRD Sec 6.2 caches it once per run), which has
no place in an automated test suite; pipeline/explain.py's own mocked tests
cover that logic.
"""

import json

import pytest

import eval.harness as harness_module
from eval.harness import run_batch
from pipeline.explain import ExplanationResult
from pipeline.models import StageTrace


def _stub_run_explanation(decision):
    result = ExplanationResult(
        reasoning_plain="stub", notification_copy_en="stub", notification_copy_hinglish="stub", generated_by="template_fallback"
    )
    trace = StageTrace(stage="explain", input_summary="stub", output_summary="stub", elapsed_ms=0.0)
    return result, trace


@pytest.fixture(autouse=True)
def _redirect_output_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(harness_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(harness_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(harness_module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(harness_module, "run_explanation", _stub_run_explanation)
    yield


def test_run_batch_produces_zero_compliance_violations_for_both_policies() -> None:
    result = run_batch(n=30, seed=1)
    assert result["results_table"]["baseline"]["compliance_violations"] == 0
    assert result["results_table"]["allocator"]["compliance_violations"] == 0


def test_run_batch_writes_results_and_run_artifact_and_log() -> None:
    result = run_batch(n=10, seed=2)
    run_id = result["run_id"]
    assert (harness_module.RESULTS_DIR / f"{run_id}.json").exists()
    assert (harness_module.RUNS_DIR / f"{run_id}.json").exists()
    assert (harness_module.LOGS_DIR / f"{run_id}.jsonl").exists()

    saved = json.loads((harness_module.RUNS_DIR / f"{run_id}.json").read_text())
    assert saved["n"] == 10
    assert len(saved["payments"]) == 10

    log_lines = (harness_module.LOGS_DIR / f"{run_id}.jsonl").read_text().strip().splitlines()
    events = [json.loads(line) for line in log_lines]
    assert events[0]["event"] == "batch_started"
    assert events[-1]["event"] == "batch_completed"


def test_allocator_never_spends_more_attempts_than_baseline_on_average() -> None:
    # The core claim: cause-aware allocation shouldn't spend MORE of the
    # scarce budget than blind fixed-schedule retry spends.
    result = run_batch(n=80, seed=3)
    baseline_spent = result["results_table"]["baseline"]["attempts_spent"]
    allocator_spent = result["results_table"]["allocator"]["attempts_spent"]
    assert allocator_spent <= baseline_spent


def test_allocator_wastes_no_attempts_on_structurally_unrecoverable_causes() -> None:
    result = run_batch(n=80, seed=4)
    assert result["results_table"]["allocator"]["attempts_wasted_on_unrecoverable_causes"] == 0


def test_run_is_reproducible_given_the_same_seed() -> None:
    a = run_batch(n=15, seed=99)
    b = run_batch(n=15, seed=99)
    assert a["results_table"] == b["results_table"]


def test_allocator_decisions_and_stage_traces_are_recorded_per_payment() -> None:
    result = run_batch(n=5, seed=5)
    payment = result["payments"][0]
    assert len(payment["allocator_decisions"]) >= 1
    assert len(payment["allocator_stage_traces"]) == len(payment["allocator_decisions"])
    first_traces = payment["allocator_stage_traces"][0]
    stages = [t["stage"] for t in first_traces]
    # payment[0] is always the first payment seen for its cause, so it also
    # gets a sample explanation (Stage 7) appended - see test below.
    assert stages[:5] == ["classify", "priors", "funding_window", "allocate", "decision"]


def test_first_payment_per_cause_gets_a_cached_explanation() -> None:
    result = run_batch(n=40, seed=7)
    seen_causes = set()
    for payment in result["payments"]:
        if payment["cause"] in seen_causes:
            assert "explanation" not in payment
            continue
        seen_causes.add(payment["cause"])
        assert "explanation" in payment
        assert payment["explanation"]["generated_by"] == "template_fallback"  # stubbed in this test


def test_raw_error_payload_is_preserved_in_run_artifact() -> None:
    result = run_batch(n=5, seed=6)
    payment = result["payments"][0]
    assert "reason" in payment["raw_error"]
