"""One-off script (Part B3): register a real test-mode UPI AutoPay mandate
end to end, attempt a subsequent charge, and try to produce a failure case.
Requires LIVE_RAZORPAY=1 and real RAZORPAY_KEY_ID/SECRET in .env. Prints
every raw response verbatim and writes them to
data/fixtures/_live_mandate_probe.json for docs/build-log.md to cite.

Never prints RAZORPAY_KEY_SECRET.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.razorpay_client import (
    FAILURE_VPA,
    SUCCESS_VPA,
    LiveRazorpayDisabled,
    charge_token,
    create_customer,
    register_mandate,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("live_mandate_probe")

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "_live_mandate_probe.json"


def main() -> None:
    results: dict = {}

    try:
        customer = create_customer("Retry Budget B3 Probe", "retrybudget.b3@example.com", "9000090003")
    except LiveRazorpayDisabled as exc:
        log.error("refusing to run: %s", exc)
        sys.exit(1)

    results["customer"] = customer
    customer_id = customer.get("id")
    log.info("customer_id=%s", customer_id)

    expire_at = int(time.time()) + 86400 * 365

    log.info("--- attempt 1: register_mandate with SUCCESS_VPA ---")
    mandate_success = register_mandate(customer_id, amount_paise=100, max_amount_paise=500000, expire_at_unix=expire_at, vpa=SUCCESS_VPA)
    results["mandate_registration_success_vpa"] = mandate_success
    log.info("order: %s", json.dumps(mandate_success["order"], indent=2)[:500])
    log.info("authorization: %s", json.dumps(mandate_success["authorization"], indent=2)[:500])
    log.info("authorization_error: %s", mandate_success["authorization_error"])

    log.info("--- attempt 2: register_mandate with FAILURE_VPA ---")
    mandate_failure = register_mandate(customer_id, amount_paise=100, max_amount_paise=500000, expire_at_unix=expire_at, vpa=FAILURE_VPA)
    results["mandate_registration_failure_vpa"] = mandate_failure
    log.info("order: %s", json.dumps(mandate_failure["order"], indent=2)[:500])
    log.info("authorization: %s", json.dumps(mandate_failure["authorization"], indent=2)[:500])
    log.info("authorization_error: %s", mandate_failure["authorization_error"])

    # If either authorization actually returned a token, try a subsequent charge.
    for label, mandate_result in [("success_vpa", mandate_success), ("failure_vpa", mandate_failure)]:
        auth = mandate_result.get("authorization")
        token_id = None
        if isinstance(auth, dict):
            token_id = auth.get("token_id") or (auth.get("token") or {}).get("id")
        if token_id:
            log.info("--- got token_id=%s from %s, attempting a subsequent charge ---", token_id, label)
            try:
                charge = charge_token(token_id, mandate_result["order"]["id"], customer_id, amount_paise=100)
                results[f"charge_against_{label}_token"] = charge
                log.info("charge result: %s", json.dumps(charge, indent=2)[:500])
            except Exception as exc:  # noqa: BLE001 - a probe must capture any failure shape
                results[f"charge_against_{label}_token_error"] = {"exception_type": type(exc).__name__, "message": str(exc)}
                log.info("charge failed: %s: %s", type(exc).__name__, exc)
        else:
            log.info("no token_id from %s authorization - nothing to charge against", label)

    OUT_PATH.write_text(json.dumps(results, indent=2, default=str))
    log.info("wrote full results to %s", OUT_PATH)


if __name__ == "__main__":
    main()
