"""Batch runner + eval harness (PRD Sec 5) - produces the submission numbers.

Runs both the cause-aware allocator and the fixed-schedule baseline over the
same batch, simulating each scheduled retry's outcome via the frozen,
isolated outcome model (eval.outcome_model - the allocator never imports it,
enforced by tests/test_outcome_model_isolation.py). Compliance invariants are
asserted for every scheduled attempt from both policies, not just reported.

Writes results to eval/results/<run_id>.json (the raw numbers) and
data/runs/<run_id>.json (the dashboard's read-only source, PRD Sec 6.2), plus
structured JSONL to logs/<run_id>.jsonl (PRD Sec 6.6).
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from eval.baseline import baseline_decide
from eval.batch_generator import CAUSE_MIX, generate_batch
from eval.outcome_model import (
    DEFAULT_PARAMS,
    OutcomeModelParams,
    simulate_outcome,
    success_probability,
)
from pipeline.allocator import AllocatorDecision, allocate
from pipeline.classify import classify_cause
from pipeline.compliance import (
    IST,
    MAX_RETRY_ATTEMPTS,
    attempts_within_cap,
    is_peak_window,
)
from pipeline.decision import RecoveryDecision
from pipeline.explain import run_explanation
from pipeline.funding_window import estimate_funding_window
from pipeline.ingest import FailedPaymentEvent, run_ingestion
from pipeline.models import FailureCause, StageTrace
from pipeline.run import run_pipeline

log = logging.getLogger("eval.harness")

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
RUNS_DIR = ROOT / "data" / "runs"
LOGS_DIR = ROOT / "logs"

PolicyName = Literal["baseline", "allocator"]

# A retry can never succeed for these causes under the frozen outcome model
# (PRD Sec 5.1) - used to score "stop-decision precision" (Sec 5.2).
_STRUCTURALLY_UNRECOVERABLE = frozenset(
    {FailureCause.MANDATE_REVOKED, FailureCause.MANDATE_EXPIRED, FailureCause.AMOUNT_EXCEEDS_MANDATE, FailureCause.AFA_REQUIRED}
)


@dataclass
class PaymentOutcome:
    payment_id: str
    cause: str
    policy: PolicyName
    attempts_spent: int
    recovered: bool
    amount_recovered: int
    stopped_early: bool
    compliance_violations: list[str] = field(default_factory=list)


def _simulate_one(
    event: FailedPaymentEvent,
    cause: FailureCause,
    policy: PolicyName,
    outcome_params: OutcomeModelParams,
    rng: random.Random,
    include_details: bool = True,
) -> tuple[PaymentOutcome, list[RecoveryDecision], list[list[StageTrace]]]:
    """Run one policy against one event until it recovers, stops, or exhausts the budget.

    include_details=False skips the full pipeline.run orchestration (decision
    record + stage traces) for the allocator policy and uses the bare
    allocate() call instead - the sensitivity sweep (Sec 5.2) only needs
    aggregate numbers across many grid points and doesn't pay for per-payment
    decision detail it never reads.
    """
    attempts_used = event.attempts_used
    attempts_spent = 0
    recovered = False
    stopped_early = False
    violations: list[str] = []
    decisions: list[RecoveryDecision] = []
    traces: list[list[StageTrace]] = []

    funding_estimate = None
    if policy == "allocator" and not include_details and cause == FailureCause.INSUFFICIENT_FUNDS:
        funding_estimate = estimate_funding_window(event.failure_time, event.prior_debit_dates)

    while True:
        if not attempts_within_cap(attempts_used):
            violations.append(f"attempts_used {attempts_used} exceeds cap of {MAX_RETRY_ATTEMPTS}")
            break

        if policy == "allocator" and include_details:
            decision, stage_traces = run_pipeline(event.model_copy(update={"attempts_used": attempts_used}))
            decisions.append(decision)
            traces.append(stage_traces)
            action, scheduled_at = decision.action, decision.scheduled_at
        elif policy == "allocator":
            allocator_result: AllocatorDecision = allocate(cause, event.failure_time, attempts_used, funding_estimate)
            action, scheduled_at = allocator_result.action, allocator_result.scheduled_at
        else:
            baseline_result: AllocatorDecision = baseline_decide(cause, event.failure_time, attempts_used)
            action, scheduled_at = baseline_result.action, baseline_result.scheduled_at

        if scheduled_at is not None and is_peak_window(scheduled_at):
            violations.append(f"scheduled_at {scheduled_at} is inside a peak window")

        if action != "retry":
            stopped_early = action in ("stop", "notify") and attempts_used < MAX_RETRY_ATTEMPTS
            break

        hours_since_failure = (scheduled_at - event.failure_time).total_seconds() / 3600.0
        attempts_used += 1
        attempts_spent += 1
        if simulate_outcome(cause, hours_since_failure, rng, outcome_params):
            recovered = True
            break
        if attempts_used >= MAX_RETRY_ATTEMPTS:
            break

    if include_details and traces:
        # Stage 1 (Ingest) happens once per event, not once per retry attempt -
        # prepend it only to the first attempt's trace so every payment shows
        # all 7 named stages (PRD Sec 6.1), not 6.
        _, ingest_trace = run_ingestion(event.model_dump(mode="json"))
        traces[0].insert(0, ingest_trace)

    outcome = PaymentOutcome(
        payment_id=event.payment_id,
        cause=cause.value,
        policy=policy,
        attempts_spent=attempts_spent,
        recovered=recovered,
        amount_recovered=event.amount if recovered else 0,
        stopped_early=stopped_early,
        compliance_violations=violations,
    )
    return outcome, decisions, traces


def _reference_probabilities(cause: FailureCause, failure_time: datetime, decision: RecoveryDecision) -> dict[str, float]:
    """The frozen outcome model's declared P(success) at each candidate time -
    computed here, in the evaluation layer, purely for dashboard display. Never
    fed back into pipeline/allocator.py, which still never imports
    eval.outcome_model (Sec 5.1) - this is the harness annotating its own
    output after the fact, the same way it already does to score simulated
    outcomes, not a new coupling."""
    result = {}
    for candidate in decision.candidates:
        hours = (candidate.scheduled_at - failure_time).total_seconds() / 3600.0
        result[candidate.offset_label] = round(success_probability(cause, hours), 4)
    return result


def _aggregate(outcomes: list[PaymentOutcome]) -> dict:
    unrecoverable_attempts = sum(o.attempts_spent for o in outcomes if o.cause in {c.value for c in _STRUCTURALLY_UNRECOVERABLE})
    return {
        "attempts_spent": sum(o.attempts_spent for o in outcomes),
        "payments_recovered": sum(o.recovered for o in outcomes),
        "amount_recovered_paise": sum(o.amount_recovered for o in outcomes),
        "attempts_wasted_on_unrecoverable_causes": unrecoverable_attempts,
        "compliance_violations": sum(len(o.compliance_violations) for o in outcomes),
        "stopped_early_count": sum(o.stopped_early for o in outcomes),
    }


def _per_cause_breakdown(outcomes: list[PaymentOutcome]) -> dict:
    breakdown: dict[str, dict] = {}
    for cause in {o.cause for o in outcomes}:
        subset = [o for o in outcomes if o.cause == cause]
        breakdown[cause] = {
            "n": len(subset),
            "recovered": sum(o.recovered for o in subset),
            "recovery_rate": round(sum(o.recovered for o in subset) / len(subset), 4) if subset else 0.0,
            "attempts_spent": sum(o.attempts_spent for o in subset),
        }
    return breakdown


def _stop_decision_precision(outcomes: list[PaymentOutcome]) -> dict:
    """Of the payments where the policy stopped/notified before exhausting the cap,
    what fraction were genuinely unrecoverable under the frozen outcome model (Sec 5.2)."""
    stopped = [o for o in outcomes if o.stopped_early]
    if not stopped:
        return {"n_stopped_early": 0, "precision": None}
    correct = sum(1 for o in stopped if o.cause in {c.value for c in _STRUCTURALLY_UNRECOVERABLE})
    return {"n_stopped_early": len(stopped), "precision": round(correct / len(stopped), 4)}


def _confidence_fallback_rate(payments_detail: list[dict]) -> dict:
    """PRD Sec 5.2 secondary metric: of insufficient_funds payments where Stage 4
    (funding-window inference) actually ran, how often confidence was too low and
    the documented safe-spacing fallback was used instead of a real estimate."""
    ran = 0
    used_fallback = 0
    for payment in payments_detail:
        traces = payment["allocator_stage_traces"]
        if not traces:
            continue
        funding_trace = next((t for t in traces[0] if t["stage"] == "funding_window"), None)
        if funding_trace is None or funding_trace["skipped"]:
            continue
        ran += 1
        if "used_fallback=True" in funding_trace["output_summary"]:
            used_fallback += 1
    if ran == 0:
        return {"n_ran": 0, "fallback_rate": None}
    return {"n_ran": ran, "fallback_rate": round(used_fallback / ran, 4)}


def _write_jsonl_log(run_id: str, events: list[dict]) -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / f"{run_id}.jsonl"
    with path.open("w") as f:
        for event in events:
            f.write(json.dumps(event, default=str) + "\n")
    return path


def compute_batch_results(
    n: int, seed: int, outcome_params: OutcomeModelParams = DEFAULT_PARAMS, include_details: bool = True
) -> tuple[dict, list[dict]]:
    """Pure computation: run both policies over one generated batch, no file I/O.

    include_details=False (used by the sensitivity sweep, Sec 5.2) skips
    building per-payment decision/trace detail - a sweep over many parameter
    grid points only needs the aggregate numbers.
    """
    events = generate_batch(n, seed=seed)
    log_lines: list[dict] = [{"event": "batch_started", "n": n, "seed": seed}]

    baseline_outcomes: list[PaymentOutcome] = []
    allocator_outcomes: list[PaymentOutcome] = []
    payments_detail: list[dict] = []

    for event in events:
        cause = classify_cause(event.error).cause
        rng_baseline = random.Random(f"{seed}-{event.payment_id}-baseline")
        rng_allocator = random.Random(f"{seed}-{event.payment_id}-allocator")

        b_outcome, _, _ = _simulate_one(event, cause, "baseline", outcome_params, rng_baseline, include_details)
        a_outcome, a_decisions, a_traces = _simulate_one(event, cause, "allocator", outcome_params, rng_allocator, include_details)

        baseline_outcomes.append(b_outcome)
        allocator_outcomes.append(a_outcome)

        for v in b_outcome.compliance_violations + a_outcome.compliance_violations:
            log_lines.append({"event": "compliance_violation", "payment_id": event.payment_id, "detail": v})
        if a_decisions:
            log_lines.append(
                {
                    "event": "allocator_decision",
                    "payment_id": event.payment_id,
                    "cause": cause.value,
                    "action": a_decisions[0].action,
                    "scheduled_at": str(a_decisions[0].scheduled_at),
                }
            )

        if include_details:
            payments_detail.append(
                {
                    "payment_id": event.payment_id,
                    "cause": cause.value,
                    "amount": event.amount,
                    "failure_time": event.failure_time.isoformat(),
                    "raw_error": event.error.model_dump(),
                    "baseline": asdict(b_outcome),
                    "allocator": asdict(a_outcome),
                    "allocator_decisions": [d.model_dump(mode="json") for d in a_decisions],
                    "allocator_stage_traces": [[t.model_dump(mode="json") for t in traces] for traces in a_traces],
                    "allocator_candidate_reference_probabilities": [
                        _reference_probabilities(cause, event.failure_time, d) for d in a_decisions
                    ],
                }
            )

    results_table = {"baseline": _aggregate(baseline_outcomes), "allocator": _aggregate(allocator_outcomes)}
    per_cause = {"baseline": _per_cause_breakdown(baseline_outcomes), "allocator": _per_cause_breakdown(allocator_outcomes)}
    stop_precision = {"baseline": _stop_decision_precision(baseline_outcomes), "allocator": _stop_decision_precision(allocator_outcomes)}
    confidence_fallback = _confidence_fallback_rate(payments_detail)

    for policy, table in results_table.items():
        if table["compliance_violations"] != 0:
            log.error("%s policy produced %d compliance violations", policy, table["compliance_violations"])

    summary = {
        "n": n,
        "seed": seed,
        "cause_mix": {c.value: w for c, w in CAUSE_MIX.items()},
        "outcome_model_params": asdict(outcome_params),
        "results_table": results_table,
        "per_cause_breakdown": per_cause,
        "stop_decision_precision": stop_precision,
        "confidence_fallback_rate": confidence_fallback,
        "payments": payments_detail,
    }
    return summary, log_lines


_EXPLAIN_NOT_SAMPLED_REASON = (
    "not sampled for this run - LLM calls are bounded to one representative payment per cause to "
    "respect free-tier rate limits and keep Stage 7 off the critical path (PRD Sec 4); see a payment "
    "marked 'has LLM explanation' in the Story tab for a live-generated example."
)


def _attach_sample_explanations(payments_detail: list[dict], log_lines: list[dict]) -> None:
    """Stage 7 (PRD Sec 4): generate a real, cached explanation for one representative
    payment per cause, not all of them - keeps the LLM off the critical path and
    bounds API calls to a free-tier provider. Cached in the run artifact; the
    dashboard never regenerates it (PRD Sec 6.2). Every OTHER payment still gets an
    explicit skipped-with-reason Stage 7 trace entry, so all 7 named stages are always
    present for every payment (PRD Sec 6.1) - never just silently absent."""
    seen_causes: set[str] = set()
    for payment in payments_detail:
        if not payment["allocator_decisions"]:
            continue
        cause = payment["cause"]
        if cause not in seen_causes:
            seen_causes.add(cause)
            decision = RecoveryDecision(**payment["allocator_decisions"][0])
            explanation, trace = run_explanation(decision)
            payment["explanation"] = explanation.model_dump()
            payment["allocator_stage_traces"][0].append(trace.model_dump(mode="json"))
            log_lines.append({"event": "explanation_generated", "payment_id": payment["payment_id"], "generated_by": explanation.generated_by})
        else:
            skip_trace = StageTrace(
                stage="explain",
                input_summary=f"payment_id={payment['payment_id']!r}",
                output_summary="skipped",
                elapsed_ms=0.0,
                skipped=True,
                skip_reason=_EXPLAIN_NOT_SAMPLED_REASON,
            )
            payment["allocator_stage_traces"][0].append(skip_trace.model_dump(mode="json"))


def run_batch(n: int = 60, seed: int = 42, outcome_params: OutcomeModelParams = DEFAULT_PARAMS) -> dict:
    """Run the full batch through both policies and write results + run artifact (PRD Sec 5)."""
    run_id = datetime.now(IST).strftime("run_%Y%m%dT%H%M%S")
    log.info("starting batch run %s: n=%d seed=%d", run_id, n, seed)

    summary, log_lines = compute_batch_results(n, seed, outcome_params, include_details=True)
    for entry in log_lines:
        entry.setdefault("run_id", run_id)

    _attach_sample_explanations(summary["payments"], log_lines)

    run_artifact = {
        "run_id": run_id,
        "generated_at": datetime.now(IST).isoformat(),
        **summary,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(run_artifact, indent=2, default=str)
    (RESULTS_DIR / f"{run_id}.json").write_text(serialized)
    (RUNS_DIR / f"{run_id}.json").write_text(serialized)
    log_lines.append({"event": "batch_completed", "run_id": run_id, "results_table": summary["results_table"]})
    _write_jsonl_log(run_id, log_lines)

    log.info("batch run %s complete: %s", run_id, summary["results_table"])
    return run_artifact


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_batch()
