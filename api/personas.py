"""Named live-simulator scenarios (Gap 3, PRD Sec 6.2's opt-in live mode).

Each persona's error object is loaded from data/fixtures/ - the same
Razorpay-shaped fixtures the batch study replays (Sec 5.0) - not invented
for the demo. Amounts and history are illustrative, built to make each
persona's story legible, not drawn from the batch generator's random seed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"


class Persona(TypedDict):
    key: str
    name: str
    description: str
    cause_fixture: str  # data/fixtures/<cause_fixture>.json
    amount: int  # paise
    attempts_used: int
    prior_debit_days_ago: list[int]  # for funding-window history, days before "now"
    prior_debit_day_of_month: int | None  # consistent day-of-month across those debits


PERSONAS: list[Persona] = [
    {
        "key": "priya",
        "name": "Priya",
        "description": "Insufficient funds - has a consistent debit history, so funding-window inference gets a real, non-fallback estimate.",
        "cause_fixture": "insufficient_funds",
        "amount": 149900,
        "attempts_used": 0,
        "prior_debit_days_ago": [30, 60, 90, 120],
        "prior_debit_day_of_month": 5,
    },
    {
        "key": "rahul",
        "name": "Rahul",
        "description": "Mandate expired - structurally unrecoverable. Baseline would still burn all 3 attempts on this; the allocator spends zero.",
        "cause_fixture": "mandate_expired",
        "amount": 29900,
        "attempts_used": 0,
        "prior_debit_days_ago": [],
        "prior_debit_day_of_month": None,
    },
    {
        "key": "ananya",
        "name": "Ananya",
        "description": "Bank technical error - transient, recoverable, short-horizon. The allocator retries soon rather than waiting.",
        "cause_fixture": "bank_technical",
        "amount": 89900,
        "attempts_used": 0,
        "prior_debit_days_ago": [],
        "prior_debit_day_of_month": None,
    },
    {
        "key": "karan",
        "name": "Karan",
        "description": "Additional-factor-authentication required - a genuine 3-way disagreement: baseline blindly retries (can't work, RBI requires fresh customer authentication), the allocator correctly notifies instead of retrying or stopping outright.",
        "cause_fixture": "afa_required",
        "amount": 1650000,  # above the RBI AFA threshold context (PRD Sec 2)
        "attempts_used": 0,
        "prior_debit_days_ago": [],
        "prior_debit_day_of_month": None,
    },
]

_PERSONAS_BY_KEY = {p["key"]: p for p in PERSONAS}


def get_persona(key: str) -> Persona:
    if key not in _PERSONAS_BY_KEY:
        raise KeyError(f"unknown persona {key!r}")
    return _PERSONAS_BY_KEY[key]


def load_fixture_error(cause_fixture: str) -> dict:
    raw = json.loads((FIXTURES_DIR / f"{cause_fixture}.json").read_text())
    raw.pop("_fixture_source", None)
    return raw
