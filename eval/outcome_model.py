"""Frozen outcome model (PRD Sec 5.1).

Declares the "true" probability that a scheduled retry succeeds, authored
independently of pipeline/allocator.py and before any allocator tuning. The
allocator MUST NEVER import this module - evaluating the allocator against a
model it can see would be circular (Sec 5.1). Enforced mechanically by
tests/test_outcome_model_isolation.py, not just by convention.

Parameters are declared, not fit to observed data (PRD Sec 8: the failure mix
and outcome model are modelled, not observed - state this in RESULTS.md).
Sensitivity to these parameters is swept in eval/sensitivity.py (Sec 5.2).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from pipeline.models import FailureCause


@dataclass(frozen=True)
class OutcomeModelParams:
    """Tunable parameters - eval/sensitivity.py (Sec 5.2) varies these.

    - funding_event_day / funding_event_spread_days: insufficient_funds
      success is modelled as a Gaussian bump in days-since-failure, centered
      on when the customer is typically funded again (e.g. a salary credit)
      and decaying with distance from it in either direction - a late retry
      is no better than an early one once the funding moment has passed.
    - insufficient_funds_peak_probability: P(success) exactly at the funding
      event.
    - bank_technical_initial_probability / bank_technical_half_life_hours:
      bank_technical decays exponentially from an initial high probability -
      transient infra issues resolve fast, so waiting doesn't help.
    """

    seed: int = 42
    funding_event_day: float = 3.0
    funding_event_spread_days: float = 1.5
    insufficient_funds_peak_probability: float = 0.55
    bank_technical_initial_probability: float = 0.8
    bank_technical_half_life_hours: float = 36.0
    unknown_probability: float = 0.05


DEFAULT_PARAMS = OutcomeModelParams()

# Causes a retry can never recover, by definition (PRD Sec 5.1): a dead or
# too-small mandate, or a debit that legally requires fresh customer
# authentication a silent retry cannot supply.
_ALWAYS_ZERO = frozenset(
    {
        FailureCause.MANDATE_REVOKED,
        FailureCause.MANDATE_EXPIRED,
        FailureCause.AMOUNT_EXCEEDS_MANDATE,
        FailureCause.AFA_REQUIRED,
    }
)


def success_probability(
    cause: FailureCause, hours_since_failure: float, params: OutcomeModelParams = DEFAULT_PARAMS
) -> float:
    """The declared 'true' probability a retry at this offset succeeds (PRD Sec 5.1)."""
    if cause in _ALWAYS_ZERO:
        return 0.0
    if cause == FailureCause.UNKNOWN:
        return params.unknown_probability
    if cause == FailureCause.BANK_TECHNICAL:
        decay = 0.5 ** (hours_since_failure / params.bank_technical_half_life_hours)
        return params.bank_technical_initial_probability * decay
    if cause == FailureCause.INSUFFICIENT_FUNDS:
        days_since_failure = hours_since_failure / 24.0
        distance = days_since_failure - params.funding_event_day
        gaussian = math.exp(-0.5 * (distance / params.funding_event_spread_days) ** 2)
        return params.insufficient_funds_peak_probability * gaussian
    raise ValueError(f"no outcome model branch defined for cause {cause!r}")


def default_rng(params: OutcomeModelParams = DEFAULT_PARAMS) -> random.Random:
    """A seeded RNG for reproducible simulation runs (PRD Sec 5.1)."""
    return random.Random(params.seed)


def simulate_outcome(
    cause: FailureCause, hours_since_failure: float, rng: random.Random, params: OutcomeModelParams = DEFAULT_PARAMS
) -> bool:
    """Draw one Bernoulli outcome from the declared probability - the simulated 'did it succeed'."""
    return rng.random() < success_probability(cause, hours_since_failure, params)
