"""Property-based fuzzing of Stage 1 ingestion (PRD Sec 4).

Extends fuzzing coverage beyond Stage 2 (tests/test_classify_fuzz.py) and
Stage 5 (tests/test_allocator_fuzz.py) to the actual data-entry boundary -
every field with an explicit Pydantic constraint (attempts_used and amount
from 2026-09-14; billing_cycle_successes added 2026-09-15 once it went
from unconstrained scaffolding to an actually-consumed field) gets checked
over a wide generated range here, not just the handful of hand-picked
values in tests/test_ingest.py.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from pipeline.compliance import MAX_RETRY_ATTEMPTS
from pipeline.ingest import ingest

_VALID_BASE = {
    "payment_id": "pay_TEST001",
    "token_id": "token_TEST001",
    "customer_id": "cust_TEST001",
    "amount": 50000,
    "error": {"code": "BAD_REQUEST_ERROR", "reason": "insufficient_funds"},
    "attempts_used": 0,
    "failure_time": "2026-09-03T08:00:00+05:30",
}


@given(amount=st.integers(min_value=-10_000_000, max_value=0))
@settings(max_examples=300)
def test_non_positive_amount_always_rejected(amount: int) -> None:
    with pytest.raises(ValidationError):
        ingest(dict(_VALID_BASE, amount=amount))


@given(
    attempts_used=st.integers(min_value=-1000, max_value=1000).filter(lambda x: not (0 <= x <= MAX_RETRY_ATTEMPTS))
)
@settings(max_examples=300)
def test_out_of_range_attempts_used_always_rejected(attempts_used: int) -> None:
    with pytest.raises(ValidationError):
        ingest(dict(_VALID_BASE, attempts_used=attempts_used))


@given(
    amount=st.integers(min_value=1, max_value=10_000_000),
    attempts_used=st.integers(min_value=0, max_value=MAX_RETRY_ATTEMPTS),
)
@settings(max_examples=300)
def test_every_in_range_value_is_accepted_and_preserved_exactly(amount: int, attempts_used: int) -> None:
    # The other half of the property: the boundary must not be so tight it
    # rejects valid data. A validator that silently coerced or clamped a
    # value instead of preserving it exactly would be its own bug on a
    # money field.
    event = ingest(dict(_VALID_BASE, amount=amount, attempts_used=attempts_used))
    assert event.amount == amount
    assert event.attempts_used == attempts_used


@given(billing_cycle_successes=st.integers(min_value=-1000, max_value=1000).filter(lambda x: not (0 <= x <= 1)))
@settings(max_examples=300)
def test_out_of_range_billing_cycle_successes_always_rejected(billing_cycle_successes: int) -> None:
    # Third field to gain a Pydantic constraint (docs/build-log.md,
    # 2026-09-15) - same fuzzing treatment as the other two once it went
    # from unconstrained scaffolding to an actually-consumed field.
    with pytest.raises(ValidationError):
        ingest(dict(_VALID_BASE, billing_cycle_successes=billing_cycle_successes))


@given(payment_id=st.text(min_size=1, max_size=200), token_id=st.text(min_size=1, max_size=200))
@settings(max_examples=200)
def test_arbitrary_id_strings_never_crash_ingestion(payment_id: str, token_id: str) -> None:
    # payment_id/token_id/customer_id are unconstrained strings by design
    # (no format Razorpay guarantees to validate against) - the property
    # here is only that no arbitrary string input crashes the boundary,
    # not that some strings are rejected.
    event = ingest(dict(_VALID_BASE, payment_id=payment_id, token_id=token_id))
    assert event.payment_id == payment_id
    assert event.token_id == token_id
