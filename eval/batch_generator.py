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

from pipeline.compliance import IST, is_peak_window
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

# Amounts are drawn from round rupee price points (subscriptions are priced in
# whole rupees, not random paise). Ordinary debits stay under the RBI
# additional-factor-authentication threshold of Rs 15,000; AFA events sit above it.
_PRICE_POINTS_RUPEES = (99, 149, 199, 299, 499, 799, 999, 1499, 1999, 2499, 4999, 5999, 7499, 9999, 12_999)
_AFA_PRICE_POINTS_RUPEES = (15_999, 19_999, 24_999, 49_999)
# Mandate caps are the registered maximum per debit (Razorpay UPI AutoPay mandates).
_MANDATE_CAP_RUPEES = (5_000, 10_000, 15_000)
_PAISE = 100
_DATE_SPREAD_DAYS = 30

# A fixed reference point, NOT datetime.now(). Failure times are anchored to
# this so the batch is fully reproducible given a seed - anchoring to the
# real wall clock would make each event's exact time-of-day (and therefore
# whether a candidate lands in a peak window, and therefore the final
# results) depend on when the script happens to be run, silently breaking
# the "seeded for reproducibility" guarantee this module and its tests claim.
_BATCH_ANCHOR_TIME = datetime(2026, 9, 1, 12, 0, tzinfo=IST)

# For insufficient_funds events only: what fraction have a usable debit
# history for Stage 4 (funding_window.py) to work with, and how many prior
# successful debits a customer with history has. A per-customer hidden
# "typical funded day" is drawn and their history is generated as noisy
# observations around it - the inference in pipeline/funding_window.py never
# sees this hidden day directly, only the noisy history, same information
# asymmetry as the real problem.
_PROBABILITY_OF_USABLE_HISTORY = 0.6
_MIN_PRIOR_DEBITS = 3
_MAX_PRIOR_DEBITS = 5
_PRIOR_DEBIT_DAY_NOISE = 2  # days of jitter around the hidden typical day


def _load_fixture_errors() -> dict[FailureCause, dict]:
    errors: dict[FailureCause, dict] = {}
    for cause in FailureCause:
        raw = json.loads((FIXTURES_DIR / f"{cause.value}.json").read_text())
        raw.pop("_fixture_source", None)
        errors[cause] = raw
    return errors


def _months_back(moment: datetime, months: int) -> tuple[int, int]:
    """(year, month) of `months` calendar months before `moment`."""
    index = moment.year * 12 + (moment.month - 1) - months
    return index // 12, index % 12 + 1


def _synthesize_prior_debit_dates(rng: random.Random, failure_time: datetime) -> list[datetime]:
    """A per-customer hidden 'typical funded day', observed noisily (Sec 4 Stage 4 input).

    One debit per calendar month (PRD Sec 2: at most one successful debit per
    cycle), so month arithmetic is calendar-based, not a fixed 30-day step.
    funding_window.py never sees the hidden day, only these noisy dates.
    """
    if rng.random() > _PROBABILITY_OF_USABLE_HISTORY:
        return []
    hidden_day = rng.randint(1, 28)
    n_debits = rng.randint(_MIN_PRIOR_DEBITS, _MAX_PRIOR_DEBITS)
    dates = []
    for back in range(1, n_debits + 1):
        noisy_day = max(1, min(28, hidden_day + rng.randint(-_PRIOR_DEBIT_DAY_NOISE, _PRIOR_DEBIT_DAY_NOISE)))
        year, month = _months_back(failure_time, back)
        dates.append(failure_time.replace(year=year, month=month, day=noisy_day))
    return sorted(dates)


def _offpeak_failure_time(rng: random.Random) -> datetime:
    """A failure time outside the NPCI peak windows: first attempts are made off-peak."""
    while True:
        candidate = _BATCH_ANCHOR_TIME - timedelta(days=rng.uniform(0, _DATE_SPREAD_DAYS), hours=rng.uniform(0, 24))
        if not is_peak_window(candidate):
            return candidate


def _amount_and_cap(rng: random.Random, cause: FailureCause) -> tuple[int, int]:
    """(amount, mandate cap) in paise, consistent with the failure cause."""
    if cause == FailureCause.AFA_REQUIRED:
        return rng.choice(_AFA_PRICE_POINTS_RUPEES) * _PAISE, 50_000 * _PAISE
    if cause == FailureCause.AMOUNT_EXCEEDS_MANDATE:
        # Only caps that some ordinary price point can exceed.
        cap = rng.choice([c for c in _MANDATE_CAP_RUPEES if c < max(_PRICE_POINTS_RUPEES)]) * _PAISE
        over = [p * _PAISE for p in _PRICE_POINTS_RUPEES if p * _PAISE > cap]
        return rng.choice(over), cap
    cap = rng.choice(_MANDATE_CAP_RUPEES) * _PAISE
    ordinary = [p * _PAISE for p in _PRICE_POINTS_RUPEES if p * _PAISE <= cap]
    return rng.choice(ordinary), cap


def generate_batch(n: int, seed: int = 42) -> list[FailedPaymentEvent]:
    """Synthesize n failed-payment events with the modelled cause mix (PRD Sec 5)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    rng = random.Random(seed)
    fixture_errors = _load_fixture_errors()
    causes = list(CAUSE_MIX.keys())
    weights = list(CAUSE_MIX.values())

    events = []
    for i in range(n):
        cause = rng.choices(causes, weights=weights, k=1)[0]
        failure_time = _offpeak_failure_time(rng)
        amount, mandate_cap = _amount_and_cap(rng, cause)
        prior_debit_dates = _synthesize_prior_debit_dates(rng, failure_time) if cause == FailureCause.INSUFFICIENT_FUNDS else []
        raw_event = {
            "payment_id": f"pay_SYNTH{i:05d}",
            "token_id": f"token_SYNTH{i:05d}",
            "customer_id": f"cust_SYNTH{i:05d}",
            "amount": amount,
            "mandate_max_amount": mandate_cap,
            "error": fixture_errors[cause],
            "prior_debit_dates": [d.isoformat() for d in prior_debit_dates],
            "attempts_used": 0,
            "failure_time": failure_time.isoformat(),
        }
        events.append(ingest(raw_event))
    return events
