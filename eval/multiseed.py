"""Multi-seed stability check (Part C1) - is the headline 29-vs-35 recovery
gap a property of the batch, or a property of one lucky/unlucky seed=42
draw?

The existing sensitivity sweep (eval/sensitivity.py) varies the outcome
model's *parameters* across 27 settings but always replays the exact same
seed=42 batch of 60 events. This is a different, complementary question:
re-draw the batch itself, with the same n and the same default outcome
model, across many seeds, and report the distribution rather than a single
number.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from eval.harness import compute_batch_results
from eval.sensitivity import run_sweep

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# 10 seeds, chosen before running (not cherry-picked after seeing results):
# the headline seed (42) plus 9 arbitrary others spanning small and large
# values, none hand-picked for a favorable outcome.
DEFAULT_SEEDS: tuple[int, ...] = (42, 1, 2, 3, 7, 13, 99, 137, 500, 2026)


def run_multiseed(n: int = 60, seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    """Run the batch at each seed and report the distribution of both
    policies' recovered-payment counts, not just seed=42's single draw."""
    rows = []
    for seed in seeds:
        summary, _ = compute_batch_results(n, seed, include_details=False)
        table = summary["results_table"]
        baseline, allocator = table["baseline"], table["allocator"]
        rows.append(
            {
                "seed": seed,
                "baseline_recovered": baseline["payments_recovered"],
                "allocator_recovered": allocator["payments_recovered"],
                "baseline_attempts_spent": baseline["attempts_spent"],
                "allocator_attempts_spent": allocator["attempts_spent"],
                "allocator_wins_on_raw_recovery": allocator["payments_recovered"] > baseline["payments_recovered"],
            }
        )

    baseline_recovered = [r["baseline_recovered"] for r in rows]
    allocator_recovered = [r["allocator_recovered"] for r in rows]
    gaps = [b - a for b, a in zip(baseline_recovered, allocator_recovered, strict=True)]

    result = {
        "n": n,
        "seeds": list(seeds),
        "rows": rows,
        "baseline_recovered_mean": round(statistics.fmean(baseline_recovered), 2),
        "baseline_recovered_stdev": round(statistics.pstdev(baseline_recovered), 2),
        "allocator_recovered_mean": round(statistics.fmean(allocator_recovered), 2),
        "allocator_recovered_stdev": round(statistics.pstdev(allocator_recovered), 2),
        "recovery_gap_mean": round(statistics.fmean(gaps), 2),
        "recovery_gap_stdev": round(statistics.pstdev(gaps), 2),
        "n_seeds_where_allocator_wins_on_raw_recovery": sum(r["allocator_wins_on_raw_recovery"] for r in rows),
        "n_seeds_total": len(rows),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "multiseed.json").write_text(json.dumps(result, indent=2))
    return result


def run_multiseed_sweep(n: int = 60, seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    """Is the sensitivity sweep's own headline ("advantage holds at 7/27
    grid points") stable across seeds, or a property of seed=42's batch?

    A different question from run_multiseed() above: that checks whether
    the default-parameter 29-vs-35 recovery gap is stable across re-drawn
    batches. This checks whether the *count of grid points where the
    allocator's advantage holds* - the sweep's own headline number - is
    itself stable, by running the full 27-point sweep at each seed rather
    than a single default-parameter run. 10 seeds x 27 grid points = 270
    batch computations, so this is slower than run_multiseed() and not
    meant to run in the default test suite at full size.
    """
    rows = []
    for seed in seeds:
        sweep = run_sweep(n, seed, write_output=False)
        n_holds = sum(r["allocator_advantage_holds"] for r in sweep["rows"])
        rows.append({"seed": seed, "advantage_holds_at": n_holds, "total_grid_points": len(sweep["rows"])})

    holds_counts = [r["advantage_holds_at"] for r in rows]
    result = {
        "n": n,
        "seeds": list(seeds),
        "rows": rows,
        "advantage_holds_at_mean": round(statistics.fmean(holds_counts), 2),
        "advantage_holds_at_stdev": round(statistics.pstdev(holds_counts), 2),
        "advantage_holds_at_min": min(holds_counts),
        "advantage_holds_at_max": max(holds_counts),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "multiseed_sweep.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    out = run_multiseed()
    print(json.dumps(out, indent=2))
