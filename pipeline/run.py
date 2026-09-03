"""Pipeline orchestrator (PRD Sec 4).

Stitches Stage 2 (classify) through Stage 6 (decision) together for one
already-ingested FailedPaymentEvent, collecting every stage's StageTrace -
including Stage 4 (funding-window inference), which is marked
skipped-with-reason: not built until Sec 7 build step 9, and not applicable
at all to causes other than insufficient_funds. This is exactly what Sec 6.1
asks the dashboard to render - the pipeline as it actually executed, skips
included, not just the final answer.
"""

from __future__ import annotations

from collections.abc import Callable

from pipeline.allocator import run_allocation
from pipeline.classify import run_classification
from pipeline.decision import RecoveryDecision, _template_reasoning_plain, run_decision
from pipeline.ingest import FailedPaymentEvent
from pipeline.models import Action, FailureCause, StageTrace
from pipeline.priors import run_priors


def _funding_window_trace(cause: FailureCause) -> StageTrace:
    if cause == FailureCause.INSUFFICIENT_FUNDS:
        skip_reason = "funding_window.py not built yet (PRD Sec 7 build step 9) - allocator used the documented safe-spacing fallback"
    else:
        skip_reason = f"funding-window inference only applies to insufficient_funds, not {cause.value}"
    return StageTrace(
        stage="funding_window",
        input_summary=f"cause={cause.value}",
        output_summary="skipped",
        elapsed_ms=0.0,
        skipped=True,
        skip_reason=skip_reason,
    )


def run_pipeline(
    event: FailedPaymentEvent,
    explain_plain: Callable[[FailureCause, Action], str] = _template_reasoning_plain,
) -> tuple[RecoveryDecision, list[StageTrace]]:
    """Run Stage 2 through Stage 6 for one ingested event, returning the decision and every stage's trace."""
    classification, classify_trace = run_classification(event.error)
    prior, priors_trace = run_priors(classification.cause)
    funding_trace = _funding_window_trace(classification.cause)
    allocation, allocate_trace = run_allocation(classification.cause, event.failure_time, event.attempts_used)
    decision, decision_trace = run_decision(
        event.payment_id, event.token_id, event.amount, event.error, classification, prior, allocation, explain_plain
    )

    return decision, [classify_trace, priors_trace, funding_trace, allocate_trace, decision_trace]
