# Fixtures - provenance (PRD Sec 5.0)

Says plainly what's live-captured vs documentation-sourced. This is exactly
the split Sec 5.0 asks for: "a few cases run against the live test API; the
batch replays that exact schema at volume."

## What's live (real Razorpay TEST-mode API calls, `scripts/capture_fixtures.py`)

- `POST /customers` and `POST /orders` (with a `token` object for a UPI
  recurring mandate) both succeed against the real API - see
  `_capture_attempts.json` for the real `customer_id`/`order_id` responses.
- Every `/payments/create/*` route (`create/upi`, `create/recurring`,
  `create/json`) returns `400 BAD_REQUEST_ERROR - "The requested URL was not
  found on the server."` for this account, consistently, across every
  variant tried (UPI collect, UPI intent, recurring-token charge). This is
  the real, confirmed shape of Razorpay's structured error object
  (`code`/`description`/`source`/`step`/`reason`/`metadata`), captured live.

**Finding:** headless S2S creation of a UPI AutoPay mandate/charge is gated
off for this test account. This isn't a wrong endpoint guess - the same 404
shape appears across every plausible route, and it matches an independent,
published statement that UPI recurring via Collect/Intent "is an on-demand
feature that requires requesting activation from the Razorpay Support team."
Requesting and waiting on that activation was out of scope for this build
window (PRD Sec 5.0 explicitly anticipates this exact risk and says not to
let it block the eval harness). Full evidence: `_capture_attempts.json`.

## What's documentation-sourced (`insufficient_funds.json`, `bank_technical.json`, `afa_required.json`)

Verbatim from Razorpay's own published error-code docs
(razorpay.com/docs/errors/payments/upi/, .../errors/payments/list/) - real
`code`/`description`/`source`/`reason` values Razorpay documents for these
failure classes, not invented. `_fixture_source` field in each file names
the page.

## What's provisional (`mandate_revoked.json`, `mandate_expired.json`, `amount_exceeds_mandate.json`)

Razorpay does not publish a dedicated payment-error `reason` for these three
in the generic error-code docs - they surface via the recurring token's
lifecycle status (`cancelled`/`expired`), not the charge error object, per
Razorpay's token-management docs. The `reason` strings used here
(`token_cancelled`, `token_expired`, `amount_exceeds_mandate`) are a
reasonable inference from that documented token-lifecycle behavior, not a
captured or independently-documented literal value. Flagged as provisional
in `pipeline/classify.py` and here; would be the first thing to verify if
Razorpay support activates S2S UPI on this account later.

## Schema

All fixtures share the shape `pipeline.models.RazorpayError` expects:
`code`, `description`, `source`, `step`, `reason`, plus whatever extra fields
Razorpay sends (preserved via `extra="allow"`).
