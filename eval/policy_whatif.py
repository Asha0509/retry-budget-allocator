"""Policy what-if: how the allocator's own knobs move the result (PRD Sec 5.2, Stage 4-5).

The sensitivity sweep (eval/sensitivity.py) varies the *outcome model* and
keeps the policy fixed. This is the other axis: keep the frozen outcome model
(Sec 5.1) and vary the allocator's two judgment calls -

  confidence_threshold   below it, Stage 4 ignores the inferred funding
                         window and uses safe spacing (1.01 = never trust it)
  spacing_hours          when the three retries may happen

over the same 10 pre-chosen seeds as eval/multiseed.py. The shipped defaults
(0.5, 24h/72h/7d) are not changed by this study; if another setting does
better under the outcome model, that is reported as a finding (Sec 5.2), not
quietly adopted - adopting it would be tuning the allocator to the model it
is graded against.

  python -m eval.policy_whatif
"""

from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime
from pathlib import Path

from eval.batch_generator import generate_batch
from eval.harness import IST, compute_batch_results
from eval.multiseed import DEFAULT_SEEDS
from pipeline.allocator import DEFAULT_POLICY, AllocatorPolicy
from pipeline.classify import classify_cause
from pipeline.funding_window import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    estimate_funding_window,
)
from pipeline.models import FailureCause

log = logging.getLogger("eval.policy_whatif")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = ROOT / "eval" / "results" / "policy_whatif.json"
LOGS_DIR = ROOT / "logs"

# Denser above 0.85: Stage 4's confidence on this batch generator is 0 for
# thin history and 0.87-1.0 otherwise, so all the movement is up there.
THRESHOLDS: tuple[float, ...] = (0.3, 0.5, 0.7, 0.88, 0.92, 0.96, 1.01)
SPACINGS: dict[str, tuple[int, ...]] = {
    "sooner": (12, 48, 120),
    "published": DEFAULT_POLICY.spacing_hours,
    "later": (48, 96, 168),
}


def _batch(n: int, seed: int, policy: AllocatorPolicy) -> dict:
    summary, _ = compute_batch_results(n, seed, include_details=False, allocator_policy=policy)
    return summary["results_table"]


def _stats(values: list[float]) -> dict:
    return {"mean": round(statistics.fmean(values), 2), "min": min(values), "max": max(values)}


def evaluate_point(n: int, seeds: tuple[int, ...], policy: AllocatorPolicy, baseline: dict[int, dict]) -> dict:
    """One grid point: allocator vs baseline per seed, summarised across seeds."""
    tables = {seed: _batch(n, seed, policy)["allocator"] for seed in seeds}
    gaps = [tables[s]["payments_recovered"] - baseline[s]["payments_recovered"] for s in seeds]
    return {
        "confidence_threshold": policy.confidence_threshold,
        "spacing_hours": list(policy.spacing_hours),
        "recovered": _stats([t["payments_recovered"] for t in tables.values()]),
        "rupees_recovered": _stats([round(t["amount_recovered_paise"] / 100) for t in tables.values()]),
        "attempts_spent": _stats([t["attempts_spent"] for t in tables.values()]),
        "attempts_wasted": _stats([t["attempts_wasted_on_unrecoverable_causes"] for t in tables.values()]),
        "compliance_violations": sum(t["compliance_violations"] for t in tables.values()),
        "recovered_minus_baseline": _stats(gaps),
        "seeds_matching_or_beating_baseline": sum(g >= 0 for g in gaps),
    }


def confidence_distribution(n: int, seeds: tuple[int, ...]) -> dict:
    """Stage 4 confidence for every insufficient_funds payment - explains why the threshold barely moves anything."""
    values = []
    for seed in seeds:
        for event in generate_batch(n, seed=seed):
            if classify_cause(event.error).cause == FailureCause.INSUFFICIENT_FUNDS:
                values.append(estimate_funding_window(event.failure_time, event.prior_debit_dates, 0.0).confidence)
    positive = [v for v in values if v > 0]
    return {"payments": len(values), "zero_confidence": len(values) - len(positive),
            "nonzero_min": min(positive, default=None), "nonzero_max": max(positive, default=None)}


def run_whatif(n: int = 60, seeds: tuple[int, ...] = DEFAULT_SEEDS,
               thresholds: tuple[float, ...] = THRESHOLDS, spacings: dict[str, tuple[int, ...]] = SPACINGS) -> dict:
    """Run the full grid; the baseline is policy-independent, so it is computed once per seed."""
    baseline = {seed: _batch(n, seed, DEFAULT_POLICY)["baseline"] for seed in seeds}
    points = []
    for name, spacing in spacings.items():
        for threshold in thresholds:
            point = evaluate_point(n, seeds, AllocatorPolicy(spacing_hours=spacing, confidence_threshold=threshold), baseline)
            points.append({"spacing": name, **point})
            log.info("%-9s threshold %.2f: recovered %.1f (baseline %.1f)", name, threshold, point["recovered"]["mean"],
                     statistics.fmean(b["payments_recovered"] for b in baseline.values()))
    return {
        "generated_at": datetime.now(IST).isoformat(timespec="seconds"),
        "n": n,
        "seeds": list(seeds),
        "default": {"spacing": "published", "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD},
        "spacings": {k: list(v) for k, v in spacings.items()},
        "thresholds": list(thresholds),
        "stage4_confidence": confidence_distribution(n, seeds),
        "baseline": {
            "recovered": _stats([b["payments_recovered"] for b in baseline.values()]),
            "rupees_recovered": _stats([round(b["amount_recovered_paise"] / 100) for b in baseline.values()]),
            "attempts_spent": _stats([b["attempts_spent"] for b in baseline.values()]),
            "attempts_wasted": _stats([b["attempts_wasted_on_unrecoverable_causes"] for b in baseline.values()]),
        },
        "points": points,
    }


def main() -> None:
    result = run_whatif()
    RESULTS_PATH.write_text(json.dumps(result, indent=2))
    best = max(result["points"], key=lambda p: p["recovered"]["mean"])
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with (LOGS_DIR / "policy_whatif.jsonl").open("a") as f:
        f.write(json.dumps({"event": "policy_whatif_completed", "ts": result["generated_at"], "points": len(result["points"]),
                            "violations": sum(p["compliance_violations"] for p in result["points"]),
                            "best": {k: best[k] for k in ("spacing", "confidence_threshold", "recovered")}}) + "\n")
    log.info("wrote %s; most recoveries: %s spacing at threshold %s (%s)", RESULTS_PATH.relative_to(ROOT),
             best["spacing"], best["confidence_threshold"], best["recovered"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
