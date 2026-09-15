"""Unit tests for the multi-seed stability check (Part C1)."""

import json

import pytest

import eval.multiseed as multiseed_module
from eval.multiseed import run_multiseed


@pytest.fixture(autouse=True)
def _redirect_results_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(multiseed_module, "RESULTS_DIR", tmp_path / "results")
    yield


def test_runs_one_row_per_seed() -> None:
    result = run_multiseed(n=10, seeds=(1, 2, 3))
    assert len(result["rows"]) == 3
    assert [r["seed"] for r in result["rows"]] == [1, 2, 3]


def test_writes_multiseed_json() -> None:
    run_multiseed(n=10, seeds=(1, 2))
    path = multiseed_module.RESULTS_DIR / "multiseed.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert len(saved["rows"]) == 2


def test_reports_distribution_not_just_a_single_number() -> None:
    result = run_multiseed(n=20, seeds=(1, 2, 3, 4))
    for key in (
        "baseline_recovered_mean",
        "baseline_recovered_stdev",
        "allocator_recovered_mean",
        "allocator_recovered_stdev",
        "recovery_gap_mean",
        "recovery_gap_stdev",
    ):
        assert key in result


def test_win_count_is_between_zero_and_total_seeds() -> None:
    result = run_multiseed(n=20, seeds=(1, 2, 3, 4, 5))
    assert 0 <= result["n_seeds_where_allocator_wins_on_raw_recovery"] <= result["n_seeds_total"]
    assert result["n_seeds_total"] == 5
