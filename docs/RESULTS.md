# Results

Run `run_20260904T003617` - 60 synthesized failed payments, seed 42. Reproduce
with `python -m eval.harness && python -m eval.sensitivity`. Raw output:
`eval/results/run_20260904T003617.json`, `eval/results/sensitivity.json`.

## 1. The outcome model, stated before any number (PRD Sec 5.1)

Every number below comes from a **simulation study**, not a field
measurement. Test-mode charge results are authored by us, not observed from
real bank behavior, so this is stated up front rather than left implicit.

The frozen model (`eval/outcome_model.py`, seed 42, written before the
allocator's own scoring was tuned, and never imported by `pipeline/`):

| Cause | Success probability |
|---|---|
| `mandate_revoked`, `mandate_expired`, `amount_exceeds_mandate`, `afa_required` | always 0 - a retry cannot succeed by definition |
| `insufficient_funds` | Gaussian bump peaking at 0.55, centered `funding_event_day=3.0` days after failure, spread `1.5` days |
| `bank_technical` | starts at 0.8, exponential decay with `half_life=36h` |
| `unknown` | flat 0.05 |

The honest claim this supports: **the allocator spends a scarce, capped
budget well under this stated model of the world.** Not "recovers X% of
real payments."

## 2. Headline

Cause mix (modelled from PRD Sec 2's published dominance ordering, not
observed - see Limitations):

| Policy | Attempts spent | Payments recovered | ₹ recovered | Attempts wasted on unrecoverable causes | Compliance violations |
|---|---|---|---|---|---|
| Fixed schedule (baseline) | 138 | 35 | ₹80,855 | 42 | 0 |
| Cause-aware allocator | **74** | 30 | ₹71,974 | **0** | 0 |

The allocator spends **46% fewer attempts** (74 vs 138) and wastes **zero**
attempts on causes the frozen model says can never succeed - a mandate that's
been revoked, expired, or exceeded is left alone entirely instead of burning
all 3 attempts against it, which is exactly what a fixed schedule does.

**It does not recover more raw payments at these default parameters** (30 vs
35). Section 4 explains why, backed by the sensitivity sweep, rather than
picking a friendlier parameter setting to report instead.

Zero compliance violations for both policies, asserted programmatically
against every scheduled attempt (`pipeline.compliance.attempts_within_cap`,
`is_peak_window`), not just reported as a count. The dashboard's Batch
Results view re-runs these checks live against the loaded batch in the
browser.

## 3. Per-cause breakdown

| Cause | n | Baseline recovery rate | Allocator recovery rate | Baseline attempts spent | Allocator attempts spent |
|---|---|---|---|---|---|
| `insufficient_funds` | 36 | 75% | 67% | 80 | 64 |
| `bank_technical` | 7 | 100% | 86% | 9 | 10 |
| `unknown` | 3 | 33% | 0% | 7 | 0 |
| `mandate_revoked` | 2 | 0% | 0% | 6 | 0 |
| `mandate_expired` | 2 | 0% | 0% | 6 | 0 |
| `amount_exceeds_mandate` | 4 | 0% | 0% | 12 | 0 |
| `afa_required` | 6 | 0% | 0% | 18 | 0 |

The pattern: for the four structurally-unrecoverable causes (14 of 60
payments), the allocator spends **0** attempts while baseline spends **42** -
every one of those is a wasted attempt under the frozen model, by
definition. For `unknown`, the allocator's conservative choice (notify
rather than blind-retry) costs it 1 recovered payment baseline got by luck
(the model gives `unknown` a nonzero 5% chance) - a real, small trade-off
between caution and raw recovery count, not a bug.

For the two genuinely recoverable causes, baseline's recovery rate is
*higher* per-payment (75% vs 67% for `insufficient_funds`, 100% vs 86% for
`bank_technical`) - Section 4 explains this is a timing-density effect, not
the allocator being worse at recognizing recoverability.

## 4. Sensitivity sweep (PRD Sec 5.2) - the finding that matters most

Re-ran the batch across a 3×3×3 grid: funding-event day (1.5 / 3.0 / 5.0
days after failure), funding-event spread (0.75 / 1.5 / 3.0 days), and
bank_technical decay half-life (18 / 36 / 72 hours) - 27 settings, same
seed, only the outcome model's parameters change.

**The allocator's raw-recovery-count advantage over baseline holds at only
7 of 27 grid points.** Reporting this plainly rather than picking the
favorable default: the advantage is not universal, and saying otherwise
would be exactly the kind of overstated result this project's honesty
sections exist to prevent.

**All 7 winning points share one property: `funding_event_day = 5.0`** (a
late funding event). The reason is structural, not a tuning artifact:

- Baseline's fixed schedule is day 1 / day 2 / day 3 (24h/48h/72h) - three
  attempts packed inside 3 days.
- The allocator's schedule is the PRD's own published safe-spacing fallback,
  24h/72h/**7 days** (PRD Sec 2) - wider, reaching a full week out.
- When the customer is funded late (day 5+), baseline's schedule *cannot
  reach that far* - all 3 of its attempts happen before the money arrives.
  The allocator's 7-day attempt can.
- When the customer is funded early or mid-cycle (day 1.5 or day 3, 20 of
  27 grid points), baseline's *denser* packing simply samples the Gaussian
  probability curve more times in the region where it's concentrated,
  winning on raw count even though it wastes attempts on unrecoverable
  causes elsewhere in the batch.

This is the honest shape of the result: **attempts-spent efficiency and
zero-waste-on-unrecoverable-causes hold at every single one of the 27
grid points** (see the raw sweep data); **raw recovery count is
parameter-dependent**, favoring the allocator specifically when funding
timing is late - which is exactly the gap Stage 4 (funding-window
inference) is meant to close, see below.

### Why funding-window inference didn't close this gap (yet)

`pipeline/funding_window.py` (Sec 7 build step 9) infers a likely funding
day from a customer's noisy debit history and was wired into the allocator.
Wiring it in moved the headline numbers by only 3-4 attempts / ~1 payment
recovered - not the fix this gap needed. Two real architectural reasons,
not a bug:

1. The allocator's candidate set is still only the 3 fixed safe-spacing
   offsets (24h/72h/7d). A correct funding-window estimate can only
   re-rank which of those 3 gets tried first - it can't schedule a retry
   at the actual inferred day if that day falls between offsets.
2. `eval/outcome_model.py` is population-level (one Gaussian for the whole
   batch), not per-customer, and was frozen (Sec 5.1) before this stage was
   built. Even a perfectly-inferred per-customer window doesn't change the
   probability the simulation draws from.

Fixing this properly means either letting the allocator schedule at
arbitrary inferred times (not just 3 fixed offsets) or extending the
outcome model to per-customer variation - both are real design changes
future work should make, not something patched in reaction to a
disappointing sweep number.

## 5. Stop-decision precision

Of payments the allocator stopped or notified instead of retrying (17 of
60), **82%** were genuinely unrecoverable under the frozen model. The
other 18% are `unknown`-cause payments: the classifier couldn't identify a
cause, priors.py conservatively chooses `notify` over a blind retry, but
the frozen model gives `unknown` a small nonzero (5%) success chance. This
is the same caution-vs-recovery trade-off as Section 3 - not a
misclassification, a declared conservative default.

Baseline never stops early by design (it's the naive comparator, retries
regardless of cause), so it has no stop-decision precision to report.

## 6. What did not work

- **Live Razorpay S2S UPI AutoPay integration** (Sec 5.0 integration tier)
  is gated behind a Razorpay Support activation this test account doesn't
  have - confirmed via 4 independent live probes (customer/order creation
  succeed, every `/payments/create/*` route 404s) and an independent
  published source. `data/fixtures/*.json` is built from Razorpay's own
  published error-code documentation instead, clearly labeled by
  provenance in `data/fixtures/README.md`. Full evidence:
  `data/fixtures/_capture_attempts.json`.
- **The allocator's first version repeated the same retry window on every
  attempt** (a real bug: candidate scoring didn't depend on `attempts_used`,
  so calling it again just re-picked the top-scored window). Caught by the
  sensitivity sweep showing implausibly good numbers, not a unit test -
  see `docs/build-log.md` for the full story and the fix.
- **Wiring funding-window inference into the allocator barely moved the
  numbers** - see Section 4. A real result, not a failed feature; reported
  instead of hidden.
- **The configured free-tier LLM model became unavailable mid-build**
  (404, then a second working model returned truncated JSON from a
  reasoning-heavy response). Both failures degraded cleanly to the
  template fallback with zero pipeline impact - see `docs/build-log.md`.
- **`setup.sh` had a real Razorpay test credential hardcoded in plaintext**,
  committed since the first scaffold commit. Found and fixed mid-build;
  see `docs/build-log.md`.

## 7. Limitations

- **Simulation study, not a field measurement.** Every number above is
  scored against `eval/outcome_model.py`, a declared model of the world,
  not observed customer behavior. See Section 1.
- **Failure mix is modelled, not observed.** `eval/batch_generator.py`'s
  `CAUSE_MIX` (55% insufficient_funds, etc.) is a declared assumption
  grounded in PRD Sec 2's dominance ordering, not a published exact
  breakdown - Razorpay does not publish one.
- **Funding-window inference is probabilistic and, in this build, has a
  narrow effect** - see Section 4's "why it didn't close the gap."
- **Small N.** 60 synthesized payments, not thousands. The sensitivity
  sweep (27 settings × 60 payments) is the mitigation for a single run
  proving too little on its own.
- **Two of the seven cause fixtures are provisional**
  (`mandate_revoked`/`mandate_expired`/`amount_exceeds_mandate`'s exact
  `reason` strings are inferred, not independently documented by Razorpay -
  see `data/fixtures/README.md`).
- **Compliance is demonstrated by scheduler logic, not live NPCI
  behavior.** Test mode does not enforce peak windows; this codebase's own
  assertions do (`pipeline/compliance.py`), checked in tests and re-run
  live in the dashboard.
