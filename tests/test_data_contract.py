"""The synthetic batch must obey the payment-rail rules encoded in eval.data_contract."""

import pytest

pytest.importorskip("pandera")

from eval.batch_generator import generate_batch
from eval.data_contract import check, render_markdown, run, to_frame


def test_generated_batch_passes_every_rule() -> None:
    assert not any(check(to_frame(generate_batch(500, seed=7))).values())


@pytest.mark.parametrize(
    ("update", "rule"),
    [
        ({"amount": 1_600_000, "mandate_max_amount": 5_000_000}, "rbi_afa_threshold"),
        ({"mandate_max_amount": 100}, "razorpay_mandate_cap"),
    ],
)
def test_contract_catches_violations(update: dict, rule: str) -> None:
    events = generate_batch(100, seed=1)
    # Pick an insufficient-funds event so the mutation is a genuine violation.
    idx = next(i for i, e in enumerate(events) if e.error.reason == "insufficient_funds")
    events[idx] = events[idx].model_copy(update=update)
    assert check(to_frame(events))[rule] > 0


def test_duplicate_month_history_is_caught() -> None:
    events = generate_batch(200, seed=2)
    idx = next(i for i, e in enumerate(events) if len(e.prior_debit_dates) >= 2)
    d = events[idx].prior_debit_dates
    events[idx] = events[idx].model_copy(update={"prior_debit_dates": [d[0], d[0].replace(day=min(28, d[0].day + 1))]})
    assert check(to_frame(events))["one_debit_per_cycle_history"] > 0


def test_report_states_pass_and_limits() -> None:
    text = render_markdown(run(300, 3))
    assert "PASS" in text and "What this does not show" in text
