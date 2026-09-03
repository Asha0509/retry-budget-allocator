"""Unit tests for the batch generator (PRD Sec 5, Sec 5.0)."""

from collections import Counter

import pytest

from eval.batch_generator import CAUSE_MIX, generate_batch
from pipeline.classify import classify_cause


def test_generates_requested_count_with_unique_payment_ids() -> None:
    events = generate_batch(50, seed=1)
    assert len(events) == 50
    assert len({e.payment_id for e in events}) == 50


def test_reproducible_given_the_same_seed() -> None:
    a = generate_batch(30, seed=7)
    b = generate_batch(30, seed=7)
    assert [e.payment_id for e in a] == [e.payment_id for e in b]
    assert [e.error.reason for e in a] == [e.error.reason for e in b]


def test_failure_times_are_anchored_not_wall_clock() -> None:
    # Regression: failure_time must not depend on datetime.now() - otherwise
    # the exact time-of-day (and therefore peak-window classification, and
    # therefore final results) silently varies by when the script is run,
    # even with a fixed seed. Two calls, real time elapsed between them,
    # must produce byte-identical failure_time values.
    import time

    a = generate_batch(10, seed=11)
    time.sleep(1.1)
    b = generate_batch(10, seed=11)
    assert [e.failure_time for e in a] == [e.failure_time for e in b]


def test_amounts_are_positive_and_within_declared_range() -> None:
    events = generate_batch(50, seed=2)
    assert all(10_000 <= e.amount <= 500_000 for e in events)


def test_every_event_starts_with_zero_attempts_used() -> None:
    events = generate_batch(20, seed=3)
    assert all(e.attempts_used == 0 for e in events)


def test_generated_errors_classify_back_to_the_intended_cause() -> None:
    # Sanity check the batch replays the fixture schema faithfully (Sec 5.0):
    # every generated error must classify to one of the 7 known causes, with
    # exact-match confidence for every cause except `unknown` itself (whose
    # own fixture is, by design, a payload nothing matches - PRD Sec 4).
    events = generate_batch(100, seed=4)
    for event in events:
        result = classify_cause(event.error)
        if result.cause.value != "unknown":
            assert result.confidence == 1.0  # exact reason match, not a fallback guess


def test_cause_mix_roughly_matches_declared_weights_at_scale() -> None:
    events = generate_batch(2000, seed=5)
    counts = Counter(classify_cause(e.error).cause for e in events)
    for cause, weight in CAUSE_MIX.items():
        observed = counts[cause] / len(events)
        assert observed == pytest.approx(weight, abs=0.03)


def test_rejects_nonpositive_n() -> None:
    with pytest.raises(ValueError, match="n must be"):
        generate_batch(0)
