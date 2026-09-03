"""Batch generator (PRD Sec 5, Sec 5.0).

Synthesizes N failed-payment events whose RazorpayError fields conform
exactly to the schema captured in data/fixtures/ - "the batch replays that
exact schema at volume" (Sec 5.0). The cause mix below is MODELLED, not
observed: PRD Sec 2 documents insufficient_funds as the dominant cause
(~20M AutoPay revocations/month) but does not publish an exact mix across
all 7 causes, so this distribution is a declared assumption, stated here and
in docs/RESULTS.md (Sec 8), not derived from real data.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from pipeline.compliance import IST
from pipeline.ingest import FailedPaymentEvent, ingest
from pipeline.models import FailureCause

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"

# Modelled cause mix (PRD Sec 2 dominance ordering; exact proportions are a
# declared assumption - see docs/RESULTS.md Sec 8 "what did not work" /
# limitations for why an exact published breakdown doesn't exist).
CAUSE_MIX: dict[FailureCause, float] = {
    FailureCause.INSUFFICIENT_FUNDS: 0.55,
    FailureCause.BANK_TECHNICAL: 0.15,
    FailureCause.MANDATE_REVOKED: 0.10,
    FailureCause.AFA_REQUIRED: 0.08,
    FailureCause.MANDATE_EXPIRED: 0.06,
    FailureCause.AMOUNT_EXCEEDS_MANDATE: 0.04,
    FailureCause.UNKNOWN: 0.02,
}

_MIN_AMOUNT_PAISE = 10_000  # RS 100
_MAX_AMOUNT_PAISE = 500_000  # RS 5,000
_DATE_SPREAD_DAYS = 30


def _load_fixture_errors() -> dict[FailureCause, dict]:
    errors: dict[FailureCause, dict] = {}
    for cause in FailureCause:
        raw = json.loads((FIXTURES_DIR / f"{cause.value}.json").read_text())
        raw.pop("_fixture_source", None)
        errors[cause] = raw
    return errors


def generate_batch(n: int, seed: int = 42) -> list[FailedPaymentEvent]:
    """Synthesize n failed-payment events with the modelled cause mix (PRD Sec 5)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = random.Random(seed)
    fixture_errors = _load_fixture_errors()
    causes = list(CAUSE_MIX.keys())
    weights = list(CAUSE_MIX.values())
    now = datetime.now(IST)

    events = []
    for i in range(n):
        cause = rng.choices(causes, weights=weights, k=1)[0]
        failure_time = now - timedelta(days=rng.uniform(0, _DATE_SPREAD_DAYS), hours=rng.uniform(0, 24))
        raw_event = {
            "payment_id": f"pay_SYNTH{i:05d}",
            "token_id": f"token_SYNTH{i:05d}",
            "customer_id": f"cust_SYNTH{i:05d}",
            "amount": rng.randint(_MIN_AMOUNT_PAISE, _MAX_AMOUNT_PAISE),
            "error": fixture_errors[cause],
            "attempts_used": 0,
            "failure_time": failure_time.isoformat(),
        }
        events.append(ingest(raw_event))
    return events
