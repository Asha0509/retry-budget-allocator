"""Stage 1 - ingestion (PRD Sec 4).

Parses a raw failed-payment event (webhook or test-mode charge failure) into
the typed FailedPaymentEvent every later stage consumes. Pydantic validation
is the actual ingestion work here - a malformed event fails loudly at the
boundary rather than propagating bad data downstream.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from pipeline.compliance import MAX_RETRY_ATTEMPTS
from pipeline.models import RazorpayError, StageTrace, run_stage


class FailedPaymentEvent(BaseModel):
    """Stage 1 output (PRD Sec 4): payment id, token id, amount, error object,
    mandate metadata, attempt history."""

    payment_id: str
    token_id: str
    customer_id: str
    amount: int = Field(gt=0)  # smallest currency unit (paise), matches Razorpay convention
    currency: str = "INR"
    error: RazorpayError
    # attempts_used indexes directly into ranked candidate lists downstream
    # (pipeline.allocator.allocate, eval.baseline.baseline_decide) - bounding
    # it here, at the actual ingestion boundary, is what makes this
    # docstring's "fails loudly at the boundary" claim true for this field
    # rather than aspirational.
    attempts_used: int = Field(ge=0, le=MAX_RETRY_ATTEMPTS)
    failure_time: datetime
    # Same "bound it at the boundary" reasoning as attempts_used above (PRD
    # Sec 2: at most one successful debit per cycle) - pipeline.allocator.
    # allocate() and eval.baseline.baseline_decide() both re-check this too,
    # for callers that build an AllocatorDecision without going through
    # ingest() first (eval/harness.py's include_details=False fast path).
    billing_cycle_successes: int = Field(default=0, ge=0, le=1)
    prior_debit_dates: list[datetime] = []  # Stage 4 input (PRD Sec 4) - customer's past successful debits


def ingest(raw_event: dict) -> FailedPaymentEvent:
    """Stage 1: validate a raw event into a FailedPaymentEvent (PRD Sec 4)."""
    return FailedPaymentEvent(**raw_event)


def run_ingestion(raw_event: dict) -> tuple[FailedPaymentEvent, StageTrace]:
    """Stage 1 entry point: ingest and produce a StageTrace (PRD Sec 6.1)."""
    input_summary = f"payment_id={raw_event.get('payment_id')!r}"

    def _work() -> tuple[FailedPaymentEvent, str]:
        event = ingest(raw_event)
        return event, f"token_id={event.token_id} amount={event.amount} attempts_used={event.attempts_used}"

    return run_stage("ingest", input_summary, _work)
