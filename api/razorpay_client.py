"""Isolated live Razorpay client (Part B2) - the one place in this repo that
can make a real network call to Razorpay's test-mode API.

Gated behind LIVE_RAZORPAY=1 (default off) so the batch study, the
sensitivity sweep, and CI keep running fully offline with no network calls
and no credentials required - every function here raises immediately if the
flag isn't set, rather than silently no-opping or silently going live.

Wraps exactly three calls, matching the real S2S UPI AutoPay lifecycle:
  1. create_customer   - POST /customers
  2. register_mandate  - POST /orders (with a recurring UPI token), then
                          attempt the authorization payment against it
  3. charge_token       - a subsequent charge against an already-registered
                          token_id

Uses the official `razorpay` SDK (already a declared dependency) rather
than raw HTTP, per Part B2 - a different tool for a different job than
scripts/capture_fixtures.py's raw httpx probes, which exist specifically to
inspect exact raw response shapes for fixture-building, not to be a
reusable client.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import razorpay
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Razorpay's own documented test-mode identifiers for simulating a UPI
# AutoPay outcome (razorpay.com/docs/payments/payment-gateway/test-upi-details/)
# - not invented, do not swap for a fabricated VPA.
SUCCESS_VPA = "success@razorpay"
FAILURE_VPA = "failure@razorpay"


class LiveRazorpayDisabled(RuntimeError):
    """Raised when a live call is attempted without LIVE_RAZORPAY=1 set."""


def _require_live_enabled() -> None:
    if os.environ.get("LIVE_RAZORPAY") != "1":
        raise LiveRazorpayDisabled(
            "LIVE_RAZORPAY is not set to '1' - refusing to make a real network call. "
            "This is the opt-in gate; the batch study and CI must never trip it."
        )


def _client() -> razorpay.Client:
    key_id = os.environ.get("RAZORPAY_KEY_ID")
    key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        raise LiveRazorpayDisabled("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set in .env")
    if not key_id.startswith("rzp_test_"):
        raise LiveRazorpayDisabled(f"key_id {key_id!r} does not look like a test-mode key - refusing to run")
    return razorpay.Client(auth=(key_id, key_secret))


def create_customer(name: str, email: str, contact: str) -> dict[str, Any]:
    """POST /customers - real, test-mode, non-destructive (Part B2 call 1)."""
    _require_live_enabled()
    return _client().customer.create({"name": name, "email": email, "contact": contact, "fail_existing": "0"})


def register_mandate(
    customer_id: str, amount_paise: int, max_amount_paise: int, expire_at_unix: int, vpa: str = SUCCESS_VPA
) -> dict[str, Any]:
    """Create a recurring-token order, then attempt the authorization payment
    against it (Part B2 call 2). Returns a dict with the order response and,
    if the authorization attempt didn't error at the transport level, its
    response too - callers (and docs/build-log.md) need the real response
    either way, not just on success.
    """
    _require_live_enabled()
    client = _client()
    order = client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "customer_id": customer_id,
            "method": "upi",
            "token": {"max_amount": max_amount_paise, "expire_at": expire_at_unix, "frequency": "as_presented"},
        }
    )
    order_id = order.get("id")
    auth_payload = {
        "amount": amount_paise,
        "currency": "INR",
        "order_id": order_id,
        "customer_id": customer_id,
        "recurring": "1",
        "email": "retrybudget.b2@example.com",
        "contact": "9000090002",
        "method": "upi",
        "vpa": vpa,
        "upi": {"flow": "collect", "vpa": vpa},
    }
    try:
        authorization = client.payment.createRecurring(auth_payload)
        auth_error = None
    except Exception as exc:  # noqa: BLE001 - this is a probe; any failure shape must be captured, not swallowed
        authorization = None
        auth_error = {"exception_type": type(exc).__name__, "message": str(exc)}
    return {"order": order, "authorization": authorization, "authorization_error": auth_error}


def charge_token(token_id: str, order_id: str, customer_id: str, amount_paise: int) -> dict[str, Any]:
    """A subsequent charge against an already-registered token_id (Part B2 call 3)."""
    _require_live_enabled()
    client = _client()
    return client.payment.createRecurring(
        {
            "amount": amount_paise,
            "currency": "INR",
            "order_id": order_id,
            "customer_id": customer_id,
            "token": token_id,
            "recurring": "1",
        }
    )
