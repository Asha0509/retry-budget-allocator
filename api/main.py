"""FastAPI backend for the dashboard's live simulator (Gap 3, PRD Sec 6.2's
opt-in "live mode").

Exposes the REAL pipeline over HTTP so a browser can trigger genuine
computation instead of reading a static file - the only place in this
project that runs the pipeline live against arbitrary input. The batch
study (eval/harness.py, data/runs/*.json) stays fixed and pre-computed,
completely untouched by this (PRD Sec 5.1 isolation - this never imports
eval.outcome_model either; a live "run this payment" produces a decision,
not a simulated recovered/not-recovered outcome).

Never routes to the real Razorpay API - calls only pipeline/ and eval/baseline
code already built and tested elsewhere in this repo.

Run: uvicorn api.main:app --reload --port 8000
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from api.personas import PERSONAS, get_persona, load_fixture_error
from eval.baseline import baseline_decide
from pipeline.compliance import IST
from pipeline.explain import run_explanation
from pipeline.ingest import run_ingestion
from pipeline.models import FailureCause
from pipeline.run import run_pipeline

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="Retry Budget Allocator - Live Simulator API")
app.add_middleware(
    CORSMiddleware,
    # Comma-separated list; set CORS_ORIGINS to the deployed dashboard URL in production.
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


MAX_AMOUNT_PAISE = 100_000_000  # Rs 10 lakh, far above any real AutoPay debit
MAX_RAW_ERROR_BYTES = 16_384
MAX_WEBHOOK_BYTES = 65_536
RATE_LIMIT_PER_MINUTE = int(os.environ.get("SIMULATE_RATE_LIMIT", "30"))
_recent_calls: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(client: str, now: float | None = None) -> bool:
    """Sliding one-minute window per client; protects the public live endpoint."""
    now = time.monotonic() if now is None else now
    calls = _recent_calls[client]
    while calls and now - calls[0] > 60:
        calls.popleft()
    if len(calls) >= RATE_LIMIT_PER_MINUTE:
        return True
    calls.append(now)
    return False


class SimulateRequest(BaseModel):
    persona: str | None = None
    amount: int | None = Field(default=None, gt=0, le=MAX_AMOUNT_PAISE, description="paise - a failed debit can't be for zero, negative or absurd money")
    prior_debit_day_of_month: int | None = Field(default=None, ge=1, le=28)
    n_prior_debits: int = Field(default=0, ge=0, le=24)
    cause: str | None = None  # a FailureCause value - looks up the matching real fixture
    raw_error: dict | None = None  # user-pasted raw JSON, takes precedence over `cause`
    attempts_used: int = Field(default=0, ge=0, le=3)
    billing_cycle_successes: int = Field(default=0, ge=0, le=1)

    @field_validator("raw_error")
    @classmethod
    def _raw_error_not_huge(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v)) > MAX_RAW_ERROR_BYTES:
            raise ValueError(f"raw_error larger than {MAX_RAW_ERROR_BYTES} bytes")
        return v


class SimulateResponse(BaseModel):
    payment_id: str
    amount: int
    failure_time: str
    raw_error: dict
    allocator_decision: dict
    allocator_stage_traces: list[dict]
    explanation: dict
    baseline_decision: dict
    decisions_differ: bool


def _build_prior_debit_dates(day_of_month: int | None, n: int, failure_time: datetime) -> list[datetime]:
    if not day_of_month or n <= 0:
        return []
    dates = []
    for months_back in range(1, n + 1):
        anchor = failure_time - timedelta(days=30 * months_back)
        dates.append(anchor.replace(day=min(day_of_month, 28)))
    return sorted(dates)


@app.get("/api/personas")
def list_personas() -> list[dict]:
    return PERSONAS  # type: ignore[return-value]


@app.post("/api/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest, request: Request) -> SimulateResponse:
    """Run one payment through the real pipeline live (Stages 1-7). No outcome
    simulation - PRD Sec 5.1 keeps eval/outcome_model.py exclusively batch-side.
    Rate limited per client (SIMULATE_RATE_LIMIT per minute)."""
    forwarded = request.headers.get("x-forwarded-for", "")
    client_id = forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    if _rate_limited(client_id):
        raise HTTPException(status_code=429, detail="too many simulations; wait a minute and retry")
    failure_time = datetime.now(IST)

    if req.persona:
        try:
            persona = get_persona(req.persona)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        error_dict = load_fixture_error(persona["cause_fixture"])
        amount = persona["amount"]
        attempts_used = persona["attempts_used"]
        billing_cycle_successes = persona["billing_cycle_successes"]
        if persona["prior_debit_day_of_month"]:
            prior_debit_dates = _build_prior_debit_dates(
                persona["prior_debit_day_of_month"], len(persona["prior_debit_days_ago"]), failure_time
            )
        else:
            prior_debit_dates = [failure_time - timedelta(days=d) for d in persona["prior_debit_days_ago"]]
        payment_id = f"pay_LIVE_{persona['key']}"
    else:
        if req.raw_error:
            error_dict = req.raw_error
        elif req.cause:
            try:
                cause_enum = FailureCause(req.cause)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"unknown cause {req.cause!r}") from exc
            error_dict = load_fixture_error(cause_enum.value)
        else:
            raise HTTPException(status_code=400, detail="must provide persona, cause, or raw_error")
        amount = req.amount or 100000
        attempts_used = req.attempts_used
        billing_cycle_successes = req.billing_cycle_successes
        prior_debit_dates = _build_prior_debit_dates(req.prior_debit_day_of_month, req.n_prior_debits, failure_time)
        payment_id = "pay_LIVE_custom"

    raw_event = {
        "payment_id": payment_id,
        "token_id": f"token_{payment_id}",
        "customer_id": f"cust_{payment_id}",
        "amount": amount,
        "error": error_dict,
        "attempts_used": attempts_used,
        "failure_time": failure_time.isoformat(),
        "billing_cycle_successes": billing_cycle_successes,
        "prior_debit_dates": [d.isoformat() for d in prior_debit_dates],
    }

    try:
        event, ingest_trace = run_ingestion(raw_event)
    except Exception as exc:
        log.error("live simulate: invalid payment shape: %s", exc)
        raise HTTPException(status_code=400, detail=f"invalid payment shape: {exc}") from exc

    decision, stage_traces = run_pipeline(event)
    explanation, explain_trace = run_explanation(decision)
    stage_traces = [ingest_trace, *stage_traces, explain_trace]

    cause = decision.cause
    baseline = baseline_decide(cause, event.failure_time, event.attempts_used, event.billing_cycle_successes)
    decisions_differ = decision.action != baseline.action or decision.scheduled_at != baseline.scheduled_at

    log.info(
        "live simulate: payment_id=%s cause=%s allocator_action=%s baseline_action=%s differ=%s explanation_by=%s",
        event.payment_id,
        cause.value,
        decision.action,
        baseline.action,
        decisions_differ,
        explanation.generated_by,
    )

    return SimulateResponse(
        payment_id=event.payment_id,
        amount=event.amount,
        failure_time=event.failure_time.isoformat(),
        raw_error=event.error.model_dump(),
        allocator_decision=decision.model_dump(mode="json"),
        allocator_stage_traces=[t.model_dump(mode="json") for t in stage_traces],
        explanation=explanation.model_dump(),
        baseline_decision=baseline.model_dump(mode="json"),
        decisions_differ=decisions_differ,
    )


_WEBHOOK_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "webhooks.jsonl"


@app.post("/api/webhooks/razorpay")
async def razorpay_webhook(request: Request) -> dict:
    """Minimal webhook receiver (Part B2) - logs the raw payload of mandate
    and payment events Razorpay sends, verbatim, to logs/webhooks.jsonl
    (git-ignored in bulk, same convention as the rest of /logs/).

    The body is only accepted when X-Razorpay-Signature matches an HMAC-SHA256
    of it under RAZORPAY_WEBHOOK_SECRET. With no secret configured the endpoint
    is closed (503), so an unauthenticated caller cannot write to the log.
    """
    secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="webhook receiver disabled: RAZORPAY_WEBHOOK_SECRET not set")
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BYTES:
        raise HTTPException(status_code=413, detail="webhook body too large")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, request.headers.get("X-Razorpay-Signature", "")):
        log.warning("webhook rejected: bad signature")
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="body is not JSON") from None
    _WEBHOOK_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _WEBHOOK_LOG_PATH.open("a") as f:
        f.write(
            json.dumps(
                {
                    "received_at": datetime.now(IST).isoformat(),
                    "event": payload.get("event"),
                    "payload": payload,
                    "raw_body_length": len(body),
                }
            )
            + "\n"
        )
    log.info("webhook received: event=%s", payload.get("event"))
    return {"status": "logged"}
