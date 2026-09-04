# Fixtures - provenance (PRD Sec 5.0)

What's actually live-captured versus documentation-sourced here, stated
plainly. This is the split Sec 5.0 asks for: "a few cases run against the
live test API; the batch replays that exact schema at volume."

## What's live (Razorpay TEST-mode API calls, `scripts/capture_fixtures.py`)

- `POST /customers` and `POST /orders` (with a `token` object for a UPI
  recurring mandate) both succeed against the live API — see
  `_capture_attempts.json` for the actual `customer_id`/`order_id`
  responses.
- Every `/payments/create/*` route (`create/upi`, `create/recurring`,
  `create/json`) returns `400 BAD_REQUEST_ERROR - "The requested URL was not
  found on the server."` for this account, and does so consistently across
  every variant tried (UPI collect, UPI intent, recurring-token charge).
  That's still a useful capture: it's the confirmed shape of Razorpay's
  structured error object (`code`/`description`/`source`/`step`/`reason`/
  `metadata`), taken directly from a live response.

**Finding:** headless S2S creation of a UPI AutoPay mandate/charge is gated
off for this test account. Ruled out a wrong-endpoint guess first — the
same 404 shape shows up across every plausible route — and it lines up
with an independent published statement that UPI recurring via
Collect/Intent "is an on-demand feature that requires requesting activation
from the Razorpay Support team." Requesting that activation and waiting on
it was out of scope for this build window (PRD Sec 5.0 anticipates exactly
this risk and says not to let it block the eval harness). Full evidence in
`_capture_attempts.json`.

## What's documentation-sourced (`insufficient_funds.json`, `bank_technical.json`, `afa_required.json`)

Taken verbatim from Razorpay's own published error-code docs
(razorpay.com/docs/errors/payments/upi/, .../errors/payments/list/) —
`code`/`description`/`source`/`reason` values Razorpay documents for these
failure classes, nothing invented. The `_fixture_source` field in each file
names the page it came from.

## What's provisional (`mandate_revoked.json`, `mandate_expired.json`, `amount_exceeds_mandate.json`)

Razorpay doesn't publish a dedicated payment-error `reason` for any of
these three in the generic error-code docs. They surface instead through
the recurring token's lifecycle status (`cancelled`/`expired`), per
Razorpay's token-management docs, not through the charge error object
directly. So the `reason` strings used here (`token_cancelled`,
`token_expired`, `amount_exceeds_mandate`) are inferred from that
documented token-lifecycle behavior rather than captured or independently
published. That's flagged as provisional both in `pipeline/classify.py`
and here, and would be the first thing worth verifying if Razorpay support
ever activates S2S UPI on this account.

## Schema

Every fixture matches the shape `pipeline.models.RazorpayError` expects:
`code`, `description`, `source`, `step`, `reason`, plus whatever extra
fields Razorpay sends (preserved via `extra="allow"`).
