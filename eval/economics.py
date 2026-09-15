"""Cost-per-attempt breakeven analysis (PRD Sec 5.2 extension) - not pipeline/.

The headline batch result is an unresolved trade: the allocator spends 46%
fewer attempts than the fixed-schedule baseline but recovers fewer payments
(29 vs 35, PRD run_20260904T223013). Neither number alone tells a merchant
whether to use this. This module prices both policies' net value at a
declared cost per retry attempt and finds the exact crossover: the cost
above which the allocator's attempt savings outweigh its lower recovery.

Reads an already-computed eval.harness results_table (baseline/allocator
aggregate dicts) rather than re-running the batch - this is pure arithmetic
over numbers that already exist, so it can never silently change the frozen
batch's own numbers (PRD Sec 5.1's isolation concern, extended: this module
doesn't touch the outcome model or the allocator at all, only their already-
computed aggregate output).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass(frozen=True)
class AttemptCostAssumptions:
    """Every component of what one retry attempt actually costs, named and
    declared separately rather than buried in one constant. None of these
    are authoritative - nobody publishes real figures for any of the three,
    so each is an illustrative placeholder meant to be replaced with a real
    one if you have it. The arithmetic that follows is the point, not these
    specific numbers.
    """

    # Gateway/processing/support overhead for one attempted debit. Reuses
    # the same illustrative figure docs/RESULTS.md Section 2 already
    # declares, rather than inventing a second, inconsistent number.
    gateway_cost_rupees: float = 20.0

    # PRD Sec 2: a pre-debit notification is legally required >=24h before
    # every attempt, so this is a mandatory per-attempt cost, not optional.
    # A transactional SMS/push in India typically runs a few paise to
    # roughly a rupee; this is a round illustrative middle, not a quote.
    notification_cost_rupees: float = 0.50

    # The least certain component by far: the probability that any single
    # retry attempt annoys a customer enough to revoke the mandate entirely
    # (losing ALL of that customer's future recurring revenue, not just
    # this one payment), times what that lost future revenue is worth.
    # Both halves are guesses - a merchant who has actual mandate-churn
    # data should replace both, not just the product.
    annoyance_revocation_probability_per_attempt: float = 0.01
    customer_lifetime_value_rupees: float = 2000.0

    @property
    def expected_annoyance_cost_rupees(self) -> float:
        return self.annoyance_revocation_probability_per_attempt * self.customer_lifetime_value_rupees

    @property
    def total_rupees(self) -> float:
        return self.gateway_cost_rupees + self.notification_cost_rupees + self.expected_annoyance_cost_rupees


DEFAULT_ASSUMPTIONS = AttemptCostAssumptions()


def net_value_rupees(aggregate: dict, cost_per_attempt_rupees: float) -> float:
    """Money recovered minus money spent attempting, for one policy's aggregate result."""
    amount_recovered_rupees = aggregate["amount_recovered_paise"] / 100.0
    return amount_recovered_rupees - aggregate["attempts_spent"] * cost_per_attempt_rupees


def compute_breakeven(baseline_aggregate: dict, allocator_aggregate: dict) -> float | None:
    """The exact cost per attempt at which net_value(allocator) == net_value(baseline).

    Above this cost, the allocator wins on money despite recovering fewer
    payments, because its attempt savings outweigh the lost recovery.
    Below it, baseline's extra recovered money outweighs its extra attempt
    spend. Returns None if the two policies spend the same number of
    attempts (no crossover - whichever recovers more money wins at every
    cost level, a degenerate case that doesn't occur in the current batch
    but is possible in principle if the two policies converged).
    """
    delta_amount_rupees = (
        allocator_aggregate["amount_recovered_paise"] - baseline_aggregate["amount_recovered_paise"]
    ) / 100.0
    delta_attempts = allocator_aggregate["attempts_spent"] - baseline_aggregate["attempts_spent"]
    if delta_attempts == 0:
        return None
    return delta_amount_rupees / delta_attempts


def sweep_cost_per_attempt(
    baseline_aggregate: dict, allocator_aggregate: dict, cost_values_rupees: tuple[float, ...]
) -> list[dict]:
    """Net value for both policies at each cost-per-attempt value - the shape
    of the breakeven, not just the single crossover point (mirrors how
    eval/sensitivity.py reports a swept shape rather than one number)."""
    rows = []
    for cost in cost_values_rupees:
        baseline_net = net_value_rupees(baseline_aggregate, cost)
        allocator_net = net_value_rupees(allocator_aggregate, cost)
        rows.append(
            {
                "cost_per_attempt_rupees": cost,
                "baseline_net_value_rupees": round(baseline_net, 2),
                "allocator_net_value_rupees": round(allocator_net, 2),
                "allocator_wins_on_money": allocator_net > baseline_net,
            }
        )
    return rows


# A grid spanning well below and well above the computed breakeven for the
# current batch (~Rs 157/attempt) - not derived from that number, chosen
# before computing it, so the table isn't retrofitted to flatter one figure.
_DEFAULT_SWEEP_RUPEES: tuple[float, ...] = (5.0, 20.0, 50.0, 100.0, 150.0, 200.0, 300.0, 500.0)

# Part C3: a 2D breakeven surface across the two genuinely-uncertain inputs,
# rather than one defended point for either. Gateway/notification costs are
# held fixed at their own illustrative defaults below (comparatively less
# contentious - real market rates exist for both); these two are the ones
# nobody should trust a single number for.
_PROBABILITY_GRID: tuple[float, ...] = (0.0, 0.005, 0.01, 0.02, 0.05, 0.10)
_LIFETIME_VALUE_GRID: tuple[float, ...] = (500.0, 1000.0, 2000.0, 5000.0, 10000.0)


def compute_breakeven_surface(
    baseline_aggregate: dict,
    allocator_aggregate: dict,
    gateway_cost_rupees: float = 20.0,
    notification_cost_rupees: float = 0.50,
    probability_grid: tuple[float, ...] = _PROBABILITY_GRID,
    lifetime_value_grid: tuple[float, ...] = _LIFETIME_VALUE_GRID,
) -> list[dict]:
    """2D breakeven surface (Part C3) across the mandate-revocation
    probability per attempt and the customer-lifetime-value figure - the
    two least-certain inputs to this whole analysis. One row per grid
    cell, each independently computed from the same real batch aggregates
    everything else in this module uses - not a single defended point for
    either parameter, a shape the reader inspects and substitutes their
    own numbers into.
    """
    rows = []
    for p in probability_grid:
        for ltv in lifetime_value_grid:
            expected_annoyance_cost = p * ltv
            total_cost = gateway_cost_rupees + notification_cost_rupees + expected_annoyance_cost
            baseline_net = net_value_rupees(baseline_aggregate, total_cost)
            allocator_net = net_value_rupees(allocator_aggregate, total_cost)
            rows.append(
                {
                    "annoyance_revocation_probability_per_attempt": p,
                    "customer_lifetime_value_rupees": ltv,
                    "expected_annoyance_cost_rupees": round(expected_annoyance_cost, 2),
                    "total_cost_per_attempt_rupees": round(total_cost, 2),
                    "baseline_net_value_rupees": round(baseline_net, 2),
                    "allocator_net_value_rupees": round(allocator_net, 2),
                    "allocator_wins_on_money": allocator_net > baseline_net,
                }
            )
    return rows


def run_economics(results_table: dict, assumptions: AttemptCostAssumptions = DEFAULT_ASSUMPTIONS) -> dict:
    """Compute the breakeven and sweep table for one already-computed results_table
    (eval.harness.compute_batch_results output's "results_table" key), and write
    eval/results/economics.json alongside the existing results/sensitivity.json."""
    baseline = results_table["baseline"]
    allocator = results_table["allocator"]

    breakeven = compute_breakeven(baseline, allocator)
    sweep_values = tuple(sorted({*_DEFAULT_SWEEP_RUPEES, round(breakeven, 2)} if breakeven is not None else _DEFAULT_SWEEP_RUPEES))
    sweep = sweep_cost_per_attempt(baseline, allocator, sweep_values)

    result = {
        "assumptions": {
            "gateway_cost_rupees": assumptions.gateway_cost_rupees,
            "notification_cost_rupees": assumptions.notification_cost_rupees,
            "annoyance_revocation_probability_per_attempt": assumptions.annoyance_revocation_probability_per_attempt,
            "customer_lifetime_value_rupees": assumptions.customer_lifetime_value_rupees,
            "expected_annoyance_cost_rupees": round(assumptions.expected_annoyance_cost_rupees, 4),
            "total_rupees": round(assumptions.total_rupees, 4),
        },
        "breakeven_cost_per_attempt_rupees": round(breakeven, 2) if breakeven is not None else None,
        "breakeven_note": (
            "above this cost per attempt, the allocator wins on net money despite recovering fewer "
            "payments (attempt savings outweigh lost recovery); below it, baseline wins on net money "
            "(recovering more payments outweighs its higher attempt spend)."
            if breakeven is not None
            else "baseline and allocator spent the same number of attempts in this batch - no crossover exists."
        ),
        "sweep": sweep,
        "surface": compute_breakeven_surface(baseline, allocator),
        "surface_note": (
            "one row per (revocation-probability, lifetime-value) grid cell - "
            "not a single defended number for either parameter. gateway_cost_rupees "
            "(20.0) and notification_cost_rupees (0.50) are held fixed at the "
            "illustrative defaults above for every cell."
        ),
    }
    result["surface_fraction_allocator_wins"] = round(
        sum(row["allocator_wins_on_money"] for row in result["surface"]) / len(result["surface"]), 4
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "economics.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    import sys

    run_files = sorted(RESULTS_DIR.glob("run_*.json"))
    if not run_files:
        sys.exit("no eval/results/run_*.json found - run `python -m eval.harness` first")
    latest = json.loads(run_files[-1].read_text())
    out = run_economics(latest["results_table"])
    print(json.dumps(out, indent=2))
