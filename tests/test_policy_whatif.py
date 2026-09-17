"""Tests for AllocatorPolicy and the policy what-if study (PRD Sec 5.2, Stage 4-5)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from eval.harness import compute_batch_results
from eval.policy_whatif import evaluate_point, run_whatif
from pipeline.allocator import DEFAULT_POLICY, AllocatorPolicy, allocate
from pipeline.compliance import is_peak_window
from pipeline.models import FailureCause

IST = ZoneInfo("Asia/Kolkata")


def test_default_policy_is_the_published_spacing() -> None:
    assert DEFAULT_POLICY.spacing_hours == (24, 72, 168)
    assert DEFAULT_POLICY.confidence_threshold is None


@pytest.mark.parametrize("spacing", [(24, 72), (24, 72, 168, 240), (72, 24, 168), (24, 24, 168), (0, 24, 72), (-1, 24, 72)])
def test_bad_spacing_is_rejected(spacing: tuple[int, ...]) -> None:
    with pytest.raises(ValidationError):
        AllocatorPolicy(spacing_hours=spacing)


def test_custom_spacing_sets_the_candidate_offsets_and_stays_out_of_peak_windows() -> None:
    policy = AllocatorPolicy(spacing_hours=(12, 48, 120))
    failure = datetime(2026, 9, 3, 1, 30, tzinfo=IST)  # +12h lands at 13:30, +48h at 01:30
    for attempts_used in range(3):
        decision = allocate(FailureCause.BANK_TECHNICAL, failure, attempts_used, policy=policy)
        assert decision.action == "retry"
        assert not is_peak_window(decision.scheduled_at)
        assert {c.offset_label.removesuffix("_shifted") for c in decision.candidates} == {"12h", "48h", "120h"}


def test_custom_spacing_keeps_cause_preference_by_position() -> None:
    # bank_technical prefers the soonest offset whatever the spacing is.
    failure = datetime(2026, 9, 3, 1, 30, tzinfo=IST)
    decision = allocate(FailureCause.BANK_TECHNICAL, failure, 0, policy=AllocatorPolicy(spacing_hours=(6, 30, 100)))
    assert decision.scheduled_at == datetime(2026, 9, 3, 7, 30, tzinfo=IST)


def test_non_default_policy_on_the_detailed_path_fails_loudly() -> None:
    with pytest.raises(ValueError, match="include_details=False"):
        compute_batch_results(5, 1, include_details=True, allocator_policy=AllocatorPolicy(spacing_hours=(12, 48, 120)))


def test_default_point_reproduces_the_shipped_numbers() -> None:
    shipped, _ = compute_batch_results(60, 42, include_details=False)
    baseline = {42: shipped["results_table"]["baseline"]}
    point = evaluate_point(60, (42,), DEFAULT_POLICY, baseline)
    assert point["recovered"]["mean"] == shipped["results_table"]["allocator"]["payments_recovered"]


def test_whatif_grid_never_breaks_a_compliance_invariant() -> None:
    result = run_whatif(n=30, seeds=(1, 2), thresholds=(0.5, 1.01),
                        spacings={"sooner": (12, 48, 120), "published": (24, 72, 168)})
    assert len(result["points"]) == 4
    assert all(p["compliance_violations"] == 0 for p in result["points"])
    assert all(p["attempts_spent"]["max"] <= 30 * 3 for p in result["points"])
    assert result["stage4_confidence"]["payments"] > 0
