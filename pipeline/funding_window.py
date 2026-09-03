"""Stage 4 - funding-window inference (PRD Sec 4).

From a customer's prior successful debit dates, infers the day-of-month
they're typically funded, blended with a generic salary-credit prior (day 1
of the month - a common Indian payday) when the customer's own history is
thin. Below FUNDING_CONFIDENCE_THRESHOLD (.env), falls back to the same
documented safe-spacing fallback the Stage-5 allocator's build-step-4 stub
used (PRD Sec 8: "present with confidence; fall back... when uncertain" -
this is a declared feature, not a hidden weakness).

Known simplification (declared, not hidden - PRD Sec 8 honesty section):
day-of-month is averaged linearly, not circularly, so a customer funded
consistently around a month boundary (e.g. days 29, 30, 1) would look more
scattered than they really are. Acceptable for a demo-scoped inference layer
that already falls back to safe spacing under real uncertainty; would need
circular statistics to trust near month boundaries.
"""

from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from pipeline.compliance import IST
from pipeline.models import FundingWindowEstimate, StageTrace, run_stage

# Explicit path, not a bare load_dotenv() upward search - on a slow
# filesystem (e.g. WSL's /mnt/c) that search is a real, measurable delay.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DEFAULT_CONFIDENCE_THRESHOLD = 0.5
SALARY_CREDIT_PRIOR_DAY = 1  # PRD Sec 4's "salary-credit prior" - a generic Indian payday assumption
_MIN_OBSERVATIONS_FOR_HIGH_CONFIDENCE = 3
_CYCLE_LENGTH_DAYS = 30


def _confidence_threshold() -> float:
    raw = os.environ.get("FUNDING_CONFIDENCE_THRESHOLD")
    if not raw:
        return DEFAULT_CONFIDENCE_THRESHOLD
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_CONFIDENCE_THRESHOLD


def _observed_day_and_spread(prior_debit_dates: list[datetime]) -> tuple[float, float]:
    days = [d.astimezone(IST).day for d in prior_debit_dates]
    typical = statistics.fmean(days)
    spread = statistics.pstdev(days) if len(days) > 1 else _CYCLE_LENGTH_DAYS / 2
    return typical, spread


def estimate_funding_window(
    failure_time: datetime, prior_debit_dates: list[datetime], confidence_threshold: float | None = None
) -> FundingWindowEstimate:
    """Stage 4: infer a likely funding window, or fall back when uncertain (PRD Sec 4)."""
    threshold = _confidence_threshold() if confidence_threshold is None else confidence_threshold
    n = len(prior_debit_dates)

    if n == 0:
        typical_day, spread = float(SALARY_CREDIT_PRIOR_DAY), _CYCLE_LENGTH_DAYS / 2
    else:
        observed_day, spread = _observed_day_and_spread(prior_debit_dates)
        # Blend observed evidence with the generic prior - more history pulls
        # the estimate toward what this customer actually does; thin history
        # leans on the generic prior. A declared heuristic blend, not full
        # Bayesian inference (PRD Sec 8 honesty section).
        prior_weight = 1.0 / (n + 1)
        typical_day = (1 - prior_weight) * observed_day + prior_weight * SALARY_CREDIT_PRIOR_DAY

    # Confidence rises with more, more-consistent observations; capped at 1.0.
    consistency = max(0.0, 1.0 - spread / (_CYCLE_LENGTH_DAYS / 2))
    volume = min(1.0, n / _MIN_OBSERVATIONS_FOR_HIGH_CONFIDENCE)
    confidence = round(consistency * volume, 4)

    if confidence < threshold:
        return FundingWindowEstimate(likely_window=None, confidence=confidence, used_fallback=True)

    failure_ist = failure_time.astimezone(IST)
    days_until = (typical_day - failure_ist.day) % _CYCLE_LENGTH_DAYS
    center = failure_ist + timedelta(days=days_until)
    half_width_days = max(0.5, spread / 2)
    likely_window = (center - timedelta(days=half_width_days), center + timedelta(days=half_width_days))

    return FundingWindowEstimate(likely_window=likely_window, confidence=confidence, used_fallback=False)


def run_funding_window(
    failure_time: datetime, prior_debit_dates: list[datetime], confidence_threshold: float | None = None
) -> tuple[FundingWindowEstimate, StageTrace]:
    """Stage 4 entry point: estimate and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"n_prior_debits={len(prior_debit_dates)}"

    def _work() -> tuple[FundingWindowEstimate, str]:
        estimate = estimate_funding_window(failure_time, prior_debit_dates, confidence_threshold)
        return estimate, f"confidence={estimate.confidence} used_fallback={estimate.used_fallback}"

    return run_stage("funding_window", input_summary, _work)
