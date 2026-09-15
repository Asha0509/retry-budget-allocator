"""Unit tests for the multi-seed stability checks (Part C1)."""

import json

import pytest

import eval.harness as harness_module
import eval.multiseed as multiseed_module
from eval.multiseed import run_multiseed, run_multiseed_sweep


@pytest.fixture(autouse=True)
def _redirect_results_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(multiseed_module, "RESULTS_DIR", tmp_path / "results")
    # run_multiseed_sweep() calls eval.sensitivity.run_sweep(), which writes
    # through harness_module.RESULTS_DIR (same convention as test_sensitivity.py)
    # - redirect that too or tests pollute the real eval/results/.
    monkeypatch.setattr(harness_module, "RESULTS_DIR", tmp_path / "results")
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


def test_multiseed_sweep_runs_the_full_grid_at_every_seed() -> None:
    # Small n and few seeds here deliberately - the real, committed finding
    # (n=60, the full 10-seed DEFAULT_SEEDS) takes over a minute (270 batch
    # computations) and lives in eval/results/multiseed_sweep.json, not in
    # the default test suite. This only checks the mechanics.
    result = run_multiseed_sweep(n=10, seeds=(1, 2))
    assert len(result["rows"]) == 2
    for row in result["rows"]:
        assert row["total_grid_points"] == 27
        assert 0 <= row["advantage_holds_at"] <= 27


def test_multiseed_sweep_writes_json_with_min_max_and_spread() -> None:
    run_multiseed_sweep(n=10, seeds=(1, 2, 3))
    path = multiseed_module.RESULTS_DIR / "multiseed_sweep.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["advantage_holds_at_min"] <= saved["advantage_holds_at_mean"] <= saved["advantage_holds_at_max"]


def test_multiseed_sweep_does_not_overwrite_the_canonical_sensitivity_json() -> None:
    # Regression test for a real bug caught before it was committed
    # (docs/build-log.md, 2026-09-15): run_sweep() unconditionally wrote
    # eval/results/sensitivity.json on every call, so looping it across
    # 10 seeds silently clobbered the one canonical (seed=42) committed
    # file with whichever seed ran last.
    canonical_path = harness_module.RESULTS_DIR / "sensitivity.json"
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_text('{"seed": 42, "marker": "canonical - must survive"}')

    run_multiseed_sweep(n=10, seeds=(1, 2, 3))

    assert json.loads(canonical_path.read_text())["marker"] == "canonical - must survive"
