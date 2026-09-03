"""Unit tests for Stage 3 recoverability priors (PRD Sec 4, Sec 7 build step 1)."""

import pytest

from pipeline.models import FailureCause
from pipeline.priors import get_prior, run_priors


def test_every_failure_cause_has_a_prior() -> None:
    for cause in FailureCause:
        prior = get_prior(cause)
        assert prior.cause == cause


@pytest.mark.parametrize("cause", list(FailureCause))
def test_recoverability_in_unit_range(cause: FailureCause) -> None:
    prior = get_prior(cause)
    assert 0.0 <= prior.recoverability <= 1.0


@pytest.mark.parametrize(
    "cause",
    [FailureCause.MANDATE_REVOKED, FailureCause.MANDATE_EXPIRED, FailureCause.AMOUNT_EXCEEDS_MANDATE],
)
def test_structurally_unrecoverable_causes_are_zero_and_stop(cause: FailureCause) -> None:
    prior = get_prior(cause)
    assert prior.recoverability == 0.0
    assert prior.action_shape == "stop"


def test_insufficient_funds_is_recoverable_and_timing_sensitive() -> None:
    prior = get_prior(FailureCause.INSUFFICIENT_FUNDS)
    assert prior.recoverability > 0.0
    assert prior.action_shape == "retry"


def test_bank_technical_is_recoverable_short_horizon() -> None:
    prior = get_prior(FailureCause.BANK_TECHNICAL)
    assert prior.recoverability > 0.0
    assert prior.action_shape == "retry"


def test_afa_required_is_never_silently_retried() -> None:
    prior = get_prior(FailureCause.AFA_REQUIRED)
    assert prior.action_shape != "retry"


def test_run_priors_returns_stage_trace() -> None:
    prior, trace = run_priors(FailureCause.BANK_TECHNICAL)
    assert prior.cause == FailureCause.BANK_TECHNICAL
    assert trace.stage == "priors"
    assert trace.skipped is False
    assert trace.elapsed_ms >= 0
    assert "action_shape=retry" in trace.output_summary
