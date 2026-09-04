# Results

Run `run_20260904T223013` - 60 synthesized failed payments, seed 42. Reproduce
with `python -m eval.harness && python -m eval.sensitivity`. Raw output:
`eval/results/run_20260904T223013.json`, `eval/results/sensitivity.json`.

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
| Cause-aware allocator | **74** | 29 | ₹70,792 | **0** | 0 |

The allocator spends **46% fewer attempts** (74 vs 138) and wastes **zero**
attempts on causes the frozen model says can never succeed - a mandate
that's been revoked, expired, or exceeded is left alone entirely instead of
burning all 3 attempts against it, which is exactly what a fixed schedule
does.

**It does not recover more raw payments at these default parameters** (29
vs 35). Section 4 diagnoses why - mechanically, not just by disclosure -
and Section 4 also documents a real scoring-function fix made this session
that moved the sensitivity sweep's advantage from 3/27 to 7/27 grid points.

**What this is worth in money, not just attempts** (a declared assumption,
priced the same way the outcome model itself is declared - see Section 6):
at an illustrative **₹20 per retry attempt** (blended gateway/ops/support
overhead for one attempted debit - not a published or sourced figure, no
such data exists for UPI AutoPay; substitute your own number, the
arithmetic is what matters) the allocator avoids **64 fewer attempts x ₹20
= ₹1,280** in operational overhead across this 60-payment batch (~₹21/
payment), of which **42 attempts (66% of the savings) were never spendable
on a successful outcome in the first place** - money that bought nothing
under the fixed schedule.

Zero compliance violations for both policies, asserted programmatically
against every scheduled attempt (`pipeline.compliance.attempts_within_cap`,
`is_peak_window`), not just reported as a count. The dashboard's Batch
Results view re-runs these checks live against the loaded batch in the
browser.

## 3. Per-cause breakdown

| Cause | n | Baseline recovery rate | Allocator recovery rate | Baseline attempts spent | Allocator attempts spent |
|---|---|---|---|---|---|
| `insufficient_funds` | 36 | 75% | 67% | 80 | 63 |
| `bank_technical` | 7 | 100% | 71% | 9 | 11 |
| `unknown` | 3 | 33% | 0% | 7 | 0 |
| `mandate_revoked` | 2 | 0% | 0% | 6 | 0 |
| `mandate_expired` | 2 | 0% | 0% | 6 | 0 |
| `amount_exceeds_mandate` | 4 | 0% | 0% | 12 | 0 |
| `afa_required` | 6 | 0% | 0% | 18 | 0 |

The pattern: for the four structurally-unrecoverable causes (14 of 60
payments), the allocator spends **0** attempts while baseline spends **42** -
every one of those is a wasted attempt under the frozen model, by
definition. For `unknown`, the allocator's conservative choice (notify
rather than blind-retry) costs it the 1 recovered payment baseline got by
luck (the model gives `unknown` a nonzero 5% chance) - a real, small
trade-off between caution and raw recovery count, not a bug.

For the two genuinely recoverable causes, baseline's recovery rate is
*higher* per-payment (75% vs 67% for `insufficient_funds`, 100% vs 71% for
`bank_technical`) while spending *more* attempts to get there. Section 4
diagnoses this as a timing-density effect, not the allocator being worse at
recognizing recoverability.

## 4. Diagnosing the loss, not just disclosing it (PRD Sec 5.2)

A prior version of this document disclosed that the allocator loses to
baseline on raw recovery count at most sensitivity-sweep settings, honestly,
but stopped at disclosure. This section diagnoses *why*, with a mechanical
check, not narrative alone.

### Is it a confidence problem?

Checked directly (`eval/sensitivity.py::_confidence_analysis`): logged
`cause_confidence` for every payment and cross-referenced it against every
sweep grid point's win/loss status. Finding: `cause_confidence` is bimodal
(**1.0 for 57 of 60 payments** - an exact match on the error's `reason`
field, deterministic - and **0.0 for the 3 `unknown` payments**, no
continuous values between) and **byte-identical across all 27 grid points**,
because classification doesn't depend on outcome-model parameters at all -
the same seeded batch is reused for every grid point, only the success
probabilities change. Losses cannot correlate with confidence because
confidence never varies. **This rules out low-confidence classification as
the cause.**

### It's the scoring function - and a real bug was in it

That pointed at `pipeline/allocator.py`'s `_OFFSET_WEIGHTS`. Reviewing the
`insufficient_funds` weights against their own stated rationale ("middle
checkpoint favoured over guessing too early or waiting the full week,"
implying symmetric caution) found they didn't match: the original weights
`{24: 0.6, 72: 1.0, 168: 0.8}` ranked 168h (96 hours from the 72h middle
checkpoint) *above* 24h (only 48 hours from it) - a failed first attempt's
second try went to the farthest offset before the genuinely closer one, an
internal contradiction with the heuristic's own comment. This was found by
re-reading the code's stated reasoning against its numbers, **before**
looking at how it affected the sweep - the fix (reweighting by actual
distance from the middle checkpoint, to `{24: 0.7, 72: 1.0, 168: 0.45}`) was
decided on that basis, not reverse-engineered from wanting a better number.
`bank_technical`'s weights were left untouched - its monotonic decay already
matches the outcome model's monotonic-decay shape, no contradiction to fix.

**After the fix:** the sensitivity sweep's advantage now holds at **7 of 27
grid points** (up from 3/27 before this session's fix - both numbers were
generated from the *same*, already-fixed reproducibility bug from the prior
build-log entry, so this is a clean before/after). Full reasoning and the
exact before/after numbers: `docs/build-log.md`, 2026-09-04.

### The remaining gap is structural, not a bug

Even after the fix, raw recovery count stays a near-tie or a loss at 20 of
27 settings, for a reason no scoring adjustment can close: baseline's fixed
schedule is **day 1/2/3** (24h/48h/72h - three attempts inside 3 days).
The allocator's schedule is the PRD's own published safe-spacing fallback,
**24h/72h/7 days** (PRD Sec 2) - wider, reaching a full week out. When a
customer is funded early or mid-cycle, baseline's *denser* packing samples
the Gaussian probability curve more times in the region where it's
concentrated, winning on raw count even though - per Section 2 above - it
wastes attempts on causes that can never succeed. Reweighting which of the
3 *existing* offsets gets tried in what order (this session's fix) can
narrow this gap; it cannot close it, because the offsets themselves are a
PRD-mandated input, not a tunable, and were never changed.

### Why funding-window inference didn't close this gap either

`pipeline/funding_window.py` (Sec 7 build step 9) infers a likely funding
day from a customer's noisy debit history and is wired into the allocator.
It moved the headline numbers by only a few attempts / roughly 1 payment -
not the fix this gap needed, for two structural reasons: (1) it can only
re-rank the 3 fixed offsets, not schedule at the actual inferred day if
that day falls between them; (2) `eval/outcome_model.py` is
population-level, not per-customer, and was frozen (Sec 5.1) before this
stage was built, so even a perfect per-customer estimate doesn't change the
probability the simulation draws from. **Confidence-fallback rate** (PRD
Sec 5.2 secondary metric): of the 36 `insufficient_funds` payments where
Stage 4 ran, **31% (11 of 36)** had thin or inconsistent history and fell
back to the same safe spacing the allocator was already using before Stage
4 existed.

Fixing the structural gap for real means either letting the allocator
schedule at arbitrary inferred times (not just 3 fixed offsets) or
extending the outcome model to per-customer variation - both are real
design changes future work should make, not something patched in reaction
to a disappointing sweep number.

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
  provenance in `data/fixtures/README.md`.
- **The allocator's first version repeated the same retry window on every
  attempt** - a real bug, caught by the sensitivity sweep showing
  implausibly good numbers, not a unit test. See `docs/build-log.md`.
- **The batch generator's failure times were anchored to wall-clock
  `datetime.now()`** instead of a fixed reference point, despite claiming
  to be seeded for reproducibility - re-running the identical seed produced
  different headline numbers on different days. Fixed with a fixed anchor
  timestamp and a regression test. See `docs/build-log.md`.
- **The `insufficient_funds` offset weights contradicted their own stated
  rationale** - found and fixed this session, Section 4 above.
- **Wiring funding-window inference into the allocator barely moved the
  numbers** - Section 4. A real result, not a failed feature; reported
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
- **The ₹20-per-attempt cost figure in Section 2 is an illustrative,
  declared assumption, not sourced or published data.** No public
  cost-per-retry-attempt figure exists for UPI AutoPay; the arithmetic
  (attempts saved x cost) is what's meant to be reusable, not the constant.
- **Failure mix is modelled, not observed.** `eval/batch_generator.py`'s
  `CAUSE_MIX` (55% insufficient_funds, etc.) is a declared assumption
  grounded in PRD Sec 2's dominance ordering, not a published exact
  breakdown - Razorpay does not publish one.
- **Funding-window inference is probabilistic and, in this build, has a
  narrow effect** - see Section 4.
- **Small N.** 60 synthesized payments, not thousands. The sensitivity
  sweep (27 settings x 60 payments) is the mitigation for a single run
  proving too little on its own.
- **Two of the seven cause fixtures are provisional**
  (`mandate_revoked`/`mandate_expired`/`amount_exceeds_mandate`'s exact
  `reason` strings are inferred, not independently documented by Razorpay -
  see `data/fixtures/README.md`).
- **Compliance is demonstrated by scheduler logic, not live NPCI
  behavior.** Test mode does not enforce peak windows; this codebase's own
  assertions do (`pipeline/compliance.py`), checked in tests and re-run
  live in the dashboard.
