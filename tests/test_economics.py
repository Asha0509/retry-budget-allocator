"""Unit tests for the cost-per-attempt breakeven analysis (PRD Sec 5.2 extension)."""

import json

import pytest

import eval.economics as economics_module
from eval.economics import (
    AttemptCostAssumptions,
    compute_breakeven,
    compute_breakeven_surface,
    net_value_rupees,
    run_economics,
    sweep_cost_per_attempt,
)


@pytest.fixture(autouse=True)
def _redirect_results_dir(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(economics_module, "RESULTS_DIR", tmp_path / "results")
    yield


# Real numbers from the committed batch run (eval/results/run_20260904T223013.json),
# not invented - the same figures docs/RESULTS.md reports.
_BASELINE = {"attempts_spent": 138, "amount_recovered_paise": 8085457}
_ALLOCATOR = {"attempts_spent": 74, "amount_recovered_paise": 7079158}


def test_net_value_subtracts_attempt_cost_from_recovered_amount() -> None:
    net = net_value_rupees(_ALLOCATOR, cost_per_attempt_rupees=10.0)
    assert net == pytest.approx(7079158 / 100.0 - 74 * 10.0)


def test_breakeven_matches_hand_computed_value() -> None:
    # (amount_allocator - amount_baseline) / (attempts_allocator - attempts_baseline), in rupees.
    expected = ((7079158 - 8085457) / 100.0) / (74 - 138)
    breakeven = compute_breakeven(_BASELINE, _ALLOCATOR)
    assert breakeven == pytest.approx(expected)
    assert breakeven == pytest.approx(157.23, abs=0.01)


def test_breakeven_is_none_when_attempts_spent_is_equal() -> None:
    same_attempts = {"attempts_spent": 100, "amount_recovered_paise": 5000000}
    assert compute_breakeven(same_attempts, same_attempts) is None


def test_below_breakeven_baseline_wins_above_breakeven_allocator_wins() -> None:
    breakeven = compute_breakeven(_BASELINE, _ALLOCATOR)
    below = sweep_cost_per_attempt(_BASELINE, _ALLOCATOR, (breakeven - 50,))[0]
    above = sweep_cost_per_attempt(_BASELINE, _ALLOCATOR, (breakeven + 50,))[0]
    assert below["allocator_wins_on_money"] is False
    assert above["allocator_wins_on_money"] is True


def test_default_assumptions_are_below_the_real_breakeven() -> None:
    # An honest finding, not a tuned one: at the illustrative default cost
    # (~Rs 40.50/attempt - gateway + notification + expected annoyance
    # cost), baseline currently wins on net money in the real batch. Only
    # above Rs 157.23/attempt does the allocator win. This test pins that
    # finding so a future change to the defaults can't silently flip it
    # without the change being visible in a failing test.
    breakeven = compute_breakeven(_BASELINE, _ALLOCATOR)
    assert economics_module.DEFAULT_ASSUMPTIONS.total_rupees < breakeven


def test_assumptions_total_sums_all_three_declared_components() -> None:
    a = AttemptCostAssumptions(
        gateway_cost_rupees=10.0,
        notification_cost_rupees=1.0,
        annoyance_revocation_probability_per_attempt=0.02,
        customer_lifetime_value_rupees=500.0,
    )
    assert a.expected_annoyance_cost_rupees == pytest.approx(10.0)
    assert a.total_rupees == pytest.approx(21.0)


def test_run_economics_writes_economics_json_with_real_breakeven() -> None:
    results_table = {"baseline": _BASELINE, "allocator": _ALLOCATOR}
    result = run_economics(results_table)
    path = economics_module.RESULTS_DIR / "economics.json"
    assert path.exists()
    saved = json.loads(path.read_text())
    assert saved["breakeven_cost_per_attempt_rupees"] == pytest.approx(157.23, abs=0.01)
    assert result == saved


def test_sweep_includes_the_computed_breakeven_point() -> None:
    results_table = {"baseline": _BASELINE, "allocator": _ALLOCATOR}
    result = run_economics(results_table)
    swept_costs = [row["cost_per_attempt_rupees"] for row in result["sweep"]]
    assert result["breakeven_cost_per_attempt_rupees"] in swept_costs


def test_breakeven_surface_covers_the_full_grid() -> None:
    rows = compute_breakeven_surface(_BASELINE, _ALLOCATOR)
    assert len(rows) == 6 * 5  # probability grid x lifetime-value grid


def test_breakeven_surface_never_favors_allocator_at_zero_annoyance_cost() -> None:
    # At probability 0.0, expected annoyance cost is 0 regardless of lifetime
    # value - total cost per attempt is just gateway + notification, which
    # is far below the real ~Rs 157 breakeven, so baseline must win every
    # such cell.
    rows = compute_breakeven_surface(_BASELINE, _ALLOCATOR)
    zero_prob_rows = [r for r in rows if r["annoyance_revocation_probability_per_attempt"] == 0.0]
    assert len(zero_prob_rows) == 5
    assert all(not r["allocator_wins_on_money"] for r in zero_prob_rows)


def test_breakeven_surface_favors_allocator_only_at_high_risk_high_value() -> None:
    # Real finding, not asserted blindly: the allocator only wins in the
    # high-probability/high-lifetime-value corner of the grid - 6 of 30
    # cells with the default grids. Pins that shape so a future change to
    # the grids or the cost function can't silently shift it unnoticed.
    rows = compute_breakeven_surface(_BASELINE, _ALLOCATOR)
    winning = [r for r in rows if r["allocator_wins_on_money"]]
    assert len(winning) == 6
    assert all(r["annoyance_revocation_probability_per_attempt"] >= 0.02 for r in winning)
    assert all(r["customer_lifetime_value_rupees"] >= 2000.0 for r in winning)


def test_run_economics_includes_surface_and_its_win_fraction() -> None:
    results_table = {"baseline": _BASELINE, "allocator": _ALLOCATOR}
    result = run_economics(results_table)
    assert len(result["surface"]) == 30
    assert result["surface_fraction_allocator_wins"] == pytest.approx(6 / 30)
