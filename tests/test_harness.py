"""Unit tests for the batch runner + eval harness (PRD Sec 5, Sec 7 build step 7).

Redirects eval.harness's output directories into pytest's tmp_path for every
test here - run_batch writes real files, and tests must never pollute the
actual eval/results/, data/runs/, or logs/ directories the real batch run
(and the committed sample log) live in.
"""

import json

import pytest

import eval.harness as harness_module
from eval.harness import run_batch


@pytest.fixture(autouse=True)
def _redirect_output_dirs(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(harness_module, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(harness_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(harness_module, "LOGS_DIR", tmp_path / "logs")
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
    assert [t["stage"] for t in first_traces] == ["classify", "priors", "funding_window", "allocate", "decision"]


def test_raw_error_payload_is_preserved_in_run_artifact() -> None:
    result = run_batch(n=5, seed=6)
    payment = result["payments"][0]
    assert "reason" in payment["raw_error"]
