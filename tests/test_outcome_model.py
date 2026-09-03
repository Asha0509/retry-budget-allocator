"""Unit tests for the frozen outcome model (PRD Sec 5.1, Sec 7 build step 5)."""

import random

import pytest

from eval.outcome_model import (
    DEFAULT_PARAMS,
    default_rng,
    simulate_outcome,
    success_probability,
)
from pipeline.models import FailureCause

_HOUR_SAMPLES = [0, 1, 12, 24, 48, 72, 96, 168, 240, 500]


@pytest.mark.parametrize(
    "cause",
    [FailureCause.MANDATE_REVOKED, FailureCause.MANDATE_EXPIRED, FailureCause.AMOUNT_EXCEEDS_MANDATE, FailureCause.AFA_REQUIRED],
)
@pytest.mark.parametrize("hours", _HOUR_SAMPLES)
def test_structurally_unrecoverable_causes_are_always_zero(cause: FailureCause, hours: float) -> None:
    assert success_probability(cause, hours) == 0.0


@pytest.mark.parametrize("cause", list(FailureCause))
@pytest.mark.parametrize("hours", _HOUR_SAMPLES)
def test_probability_always_in_unit_range(cause: FailureCause, hours: float) -> None:
    assert 0.0 <= success_probability(cause, hours) <= 1.0


def test_bank_technical_decays_with_time() -> None:
    p0 = success_probability(FailureCause.BANK_TECHNICAL, 0)
    p1 = success_probability(FailureCause.BANK_TECHNICAL, 36)
    p2 = success_probability(FailureCause.BANK_TECHNICAL, 168)
    assert p0 > p1 > p2
    assert p1 == pytest.approx(p0 / 2, rel=1e-6)  # one half-life in


def test_insufficient_funds_peaks_near_funding_event_and_decays_both_sides() -> None:
    peak_day_hours = DEFAULT_PARAMS.funding_event_day * 24
    p_peak = success_probability(FailureCause.INSUFFICIENT_FUNDS, peak_day_hours)
    p_early = success_probability(FailureCause.INSUFFICIENT_FUNDS, peak_day_hours - 48)
    p_late = success_probability(FailureCause.INSUFFICIENT_FUNDS, peak_day_hours + 96)
    assert p_peak == pytest.approx(DEFAULT_PARAMS.insufficient_funds_peak_probability)
    assert p_peak > p_early
    assert p_peak > p_late


def test_unknown_cause_is_low_but_nonzero() -> None:
    assert 0.0 < success_probability(FailureCause.UNKNOWN, 24) < 0.2


def test_default_rng_is_reproducible() -> None:
    rng1 = default_rng()
    rng2 = default_rng()
    draws1 = [rng1.random() for _ in range(10)]
    draws2 = [rng2.random() for _ in range(10)]
    assert draws1 == draws2


def test_simulate_outcome_is_deterministic_given_a_seeded_rng() -> None:
    outcomes_a = [simulate_outcome(FailureCause.INSUFFICIENT_FUNDS, 72, random.Random(7)) for _ in range(20)]
    outcomes_b = [simulate_outcome(FailureCause.INSUFFICIENT_FUNDS, 72, random.Random(7)) for _ in range(20)]
    assert outcomes_a == outcomes_b


def test_simulate_outcome_never_succeeds_for_zero_probability_causes() -> None:
    rng = random.Random(0)
    assert all(not simulate_outcome(FailureCause.MANDATE_REVOKED, h, rng) for h in _HOUR_SAMPLES)
