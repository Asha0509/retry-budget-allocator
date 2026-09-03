"""Sensitivity sweep (PRD Sec 5.2) - the thing that makes the headline result mean something.

A single run against one outcome model proves little, since the model was
authored by the same person as the allocator. This re-runs the same batch
(same seed, so the same generated events) across a grid of plausible
outcome-model parameter settings and reports how the allocator's advantage
over the baseline moves. If the advantage only shows up under one favourable
setting, that's the finding to report - not a result to quietly drop.
"""

from __future__ import annotations

import itertools
import json
import logging
from dataclasses import replace

from eval import harness as harness_module
from eval.harness import compute_batch_results
from eval.outcome_model import DEFAULT_PARAMS

log = logging.getLogger("eval.sensitivity")

# A small, named grid - not exhaustive, but spans early/mid/late funding
# events, tight/mid/loose clustering, and fast/mid/slow technical-failure
# recovery (PRD Sec 5.2's own examples).
_FUNDING_EVENT_DAYS = (1.5, 3.0, 5.0)
_FUNDING_EVENT_SPREAD_DAYS = (0.75, 1.5, 3.0)
_BANK_TECHNICAL_HALF_LIFE_HOURS = (18.0, 36.0, 72.0)


def _grid():
    for day, spread, half_life in itertools.product(
        _FUNDING_EVENT_DAYS, _FUNDING_EVENT_SPREAD_DAYS, _BANK_TECHNICAL_HALF_LIFE_HOURS
    ):
        yield replace(
            DEFAULT_PARAMS, funding_event_day=day, funding_event_spread_days=spread, bank_technical_half_life_hours=half_life
        )


def run_sweep(n: int = 60, seed: int = 42) -> dict:
    """Run the batch across the parameter grid and report the allocator's advantage at each point."""
    rows = []
    for params in _grid():
        summary, _ = compute_batch_results(n, seed, params, include_details=False)
        table = summary["results_table"]
        baseline, allocator = table["baseline"], table["allocator"]

        attempts_saved = baseline["attempts_spent"] - allocator["attempts_spent"]
        recovered_advantage = allocator["payments_recovered"] - baseline["payments_recovered"]
        amount_advantage_paise = allocator["amount_recovered_paise"] - baseline["amount_recovered_paise"]

        if baseline["compliance_violations"] or allocator["compliance_violations"]:
            log.error("compliance violation at grid point %s", params)

        rows.append(
            {
                "funding_event_day": params.funding_event_day,
                "funding_event_spread_days": params.funding_event_spread_days,
                "bank_technical_half_life_hours": params.bank_technical_half_life_hours,
                "baseline": baseline,
                "allocator": allocator,
                "attempts_saved": attempts_saved,
                "recovered_advantage": recovered_advantage,
                "amount_advantage_paise": amount_advantage_paise,
                "allocator_advantage_holds": attempts_saved >= 0 and recovered_advantage >= 0,
            }
        )

    n_rows = len(rows)
    n_holds = sum(r["allocator_advantage_holds"] for r in rows)
    sweep = {
        "n": n,
        "seed": seed,
        "grid_dimensions": {
            "funding_event_day": _FUNDING_EVENT_DAYS,
            "funding_event_spread_days": _FUNDING_EVENT_SPREAD_DAYS,
            "bank_technical_half_life_hours": _BANK_TECHNICAL_HALF_LIFE_HOURS,
        },
        "rows": rows,
        "advantage_holds_at_n_of_total": f"{n_holds}/{n_rows}",
    }

    harness_module.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (harness_module.RESULTS_DIR / "sensitivity.json").write_text(json.dumps(sweep, indent=2, default=str))
    log.info("sensitivity sweep complete: advantage holds at %d/%d grid points", n_holds, n_rows)
    return sweep


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_sweep()
