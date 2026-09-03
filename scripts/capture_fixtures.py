"""One-off integration-tier tool: capture real Razorpay test-mode error objects
(PRD Sec 5.0). Not part of the `pipeline` package - run manually, not imported.

Attempts to register a UPI AutoPay mandate against the live Razorpay
TEST-mode API. Customer and order creation succeed live; every
/payments/create/* route returns a consistent 404-shaped error on this
account - S2S UPI payment creation requires Razorpay Support to activate it,
which was out of scope for this build window. See data/fixtures/README.md
for the full finding and what data/fixtures/*.json is sourced from instead.
Never prints RAZORPAY_KEY_SECRET; only status codes and response bodies
(which do not contain the secret) are logged.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("capture_fixtures")

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "data" / "fixtures"
LOG_PATH = ROOT / "data" / "fixtures" / "_capture_attempts.json"

load_dotenv(ROOT / ".env")

KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")

if not KEY_ID or not KEY_SECRET:
    log.error("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set in .env - cannot run integration tier")
    sys.exit(1)

if not KEY_ID.startswith("rzp_test_"):
    log.error("RAZORPAY_KEY_ID does not look like a test-mode key (rzp_test_...) - refusing to run against live mode")
    sys.exit(1)

client = httpx.Client(base_url="https://api.razorpay.com/v1", auth=(KEY_ID, KEY_SECRET), timeout=15.0)
attempts: list[dict] = []


def call(label: str, method: str, path: str, **kwargs) -> httpx.Response:
    """Make one API call, log a sanitized record of what happened, never log secrets."""
    try:
        resp = client.request(method, path, **kwargs)
    except httpx.HTTPError as exc:
        log.error("%s: request failed - %s", label, exc)
        attempts.append({"label": label, "method": method, "path": path, "request": kwargs.get("json"), "transport_error": str(exc)})
        raise
    record = {
        "label": label,
        "method": method,
        "path": path,
        "request": kwargs.get("json"),
        "status_code": resp.status_code,
        "response": _safe_json(resp),
    }
    attempts.append(record)
    log.info("%s -> %s", label, resp.status_code)
    return resp


def _safe_json(resp: httpx.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"raw_text": resp.text[:2000]}


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    customer_resp = call(
        "create_customer",
        "POST",
        "/customers",
        json={
            "name": "Retry Budget Test Customer",
            "email": "retrybudget.test@example.com",
            "contact": "9000090000",
            "fail_existing": "0",
        },
    )
    customer = _safe_json(customer_resp)
    customer_id = customer.get("id")
    if not customer_id:
        log.error("Could not create/reuse a test customer - see data/fixtures/_capture_attempts.json for the raw error")
        _flush()
        return
    log.info("customer_id=%s", customer_id)

    expire_at = int(time.time()) + 60 * 60 * 24 * 365
    order_resp = call(
        "create_recurring_order",
        "POST",
        "/orders",
        json={
            "amount": 100,
            "currency": "INR",
            "customer_id": customer_id,
            "method": "upi",
            "token": {
                "max_amount": 500000,
                "expire_at": expire_at,
                "frequency": "as_presented",
            },
        },
    )
    order = _safe_json(order_resp)
    order_id = order.get("id")
    if not order_id:
        log.error("Order creation for the recurring UPI token failed - real error captured below, this is the finding")
        _flush()
        return
    log.info("order_id=%s", order_id)

    candidate_paths = ["/payments/create/upi", "/payments", "/payments/create/ajax"]
    for path in candidate_paths:
        resp = call(
            f"authorize_upi_mandate_try_{path.replace('/', '_')}",
            "POST",
            path,
            json={
                "amount": 100,
                "currency": "INR",
                "order_id": order_id,
                "customer_id": customer_id,
                "recurring": "1",
                "email": "retrybudget.test@example.com",
                "contact": "9000090000",
                "method": "upi",
                "vpa": "success@razorpay",
                "upi": {"flow": "collect", "vpa": "success@razorpay"},
            },
        )
        log.info("authorize via %s -> %s: %s", path, resp.status_code, _safe_json(resp))

    _flush()


def _flush() -> None:
    LOG_PATH.write_text(json.dumps(attempts, indent=2))
    log.info("wrote %s attempt records to %s", len(attempts), LOG_PATH)


if __name__ == "__main__":
    main()
