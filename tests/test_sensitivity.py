"""Unit tests for the outcome-model sensitivity sweep (PRD Sec 5.2, Sec 7 build step 8)."""

import json

import pytest

import eval.harness as harness_module
from eval.sensitivity import run_sweep


@pytest.fixture(autouse=True)
def _redirect_results_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(harness_module, "RESULTS_DIR", tmp_path / "results")
    yield


def test_sweep_covers_the_full_grid() -> None:
    sweep = run_sweep(n=10, seed=1)
    assert len(sweep["rows"]) == 3 * 3 * 3


def test_sweep_writes_sensitivity_json() -> None:
    run_sweep(n=10, seed=2)
    path = harness_module.RESULTS_DIR / "sensitivity.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert len(saved["rows"]) == 27


def test_every_grid_point_has_zero_compliance_violations() -> None:
    sweep = run_sweep(n=20, seed=3)
    for row in sweep["rows"]:
        assert row["baseline"]["compliance_violations"] == 0
        assert row["allocator"]["compliance_violations"] == 0


def test_advantage_holds_summary_reflects_the_rows() -> None:
    sweep = run_sweep(n=20, seed=4)
    n_holds = sum(r["allocator_advantage_holds"] for r in sweep["rows"])
    assert sweep["advantage_holds_at_n_of_total"] == f"{n_holds}/27"
