"""Unit tests for Stage 4 funding-window inference (PRD Sec 4, Sec 7 build step 9)."""

from datetime import datetime, timedelta

from pipeline.compliance import IST
from pipeline.funding_window import estimate_funding_window, run_funding_window


def _dt(day: int, month: int = 1, year: int = 2026) -> datetime:
    return datetime(year, month, day, 8, 0, tzinfo=IST)


def test_no_history_falls_back_to_safe_spacing() -> None:
    estimate = estimate_funding_window(_dt(3), prior_debit_dates=[], confidence_threshold=0.5)
    assert estimate.used_fallback is True
    assert estimate.likely_window is None


def test_consistent_history_produces_high_confidence_and_a_window() -> None:
    prior_dates = [_dt(5, month=1), _dt(5, month=2), _dt(6, month=3), _dt(5, month=4)]
    estimate = estimate_funding_window(_dt(1, month=5), prior_debit_dates=prior_dates, confidence_threshold=0.5)
    assert estimate.used_fallback is False
    assert estimate.confidence >= 0.5
    assert estimate.likely_window is not None
    start, end = estimate.likely_window
    assert start < end


def test_inconsistent_history_falls_back_below_threshold() -> None:
    # Wildly scattered days-of-month - low consistency, should not clear a normal threshold.
    prior_dates = [_dt(2, month=1), _dt(28, month=2), _dt(15, month=3)]
    estimate = estimate_funding_window(_dt(1, month=5), prior_debit_dates=prior_dates, confidence_threshold=0.5)
    assert estimate.used_fallback is True


def test_single_observation_has_low_confidence() -> None:
    estimate = estimate_funding_window(_dt(1, month=5), prior_debit_dates=[_dt(10, month=4)], confidence_threshold=0.9)
    assert estimate.used_fallback is True
    assert estimate.confidence < 0.9


def test_confidence_never_exceeds_one() -> None:
    prior_dates = [_dt(10, month=m) for m in range(1, 7)]
    estimate = estimate_funding_window(_dt(1, month=8), prior_debit_dates=prior_dates, confidence_threshold=0.0)
    assert estimate.confidence <= 1.0


def test_likely_window_lands_after_failure_time_within_a_cycle() -> None:
    prior_dates = [_dt(10, month=1), _dt(10, month=2), _dt(10, month=3)]
    failure = _dt(1, month=4)
    estimate = estimate_funding_window(failure, prior_debit_dates=prior_dates, confidence_threshold=0.3)
    assert estimate.used_fallback is False
    start, _ = estimate.likely_window
    assert failure <= start <= failure + timedelta(days=30)


def test_run_funding_window_returns_stage_trace() -> None:
    estimate, trace = run_funding_window(_dt(1), prior_debit_dates=[], confidence_threshold=0.5)
    assert trace.stage == "funding_window"
    assert estimate.used_fallback is True
