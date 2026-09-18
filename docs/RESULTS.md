# Results

Run `run_20261008T100907` - 60 synthesized failed payments, seed 42. Reproduce
with `python -m eval.harness && python -m eval.sensitivity`. Raw output:
`eval/results/run_20261008T100907.json`, `eval/results/sensitivity.json`.
Every number in this file was checked against those JSON files and
`docs/DATA_QUALITY.md`; the other result files are named where they are used.

| Section | What it answers |
|---|---|
| 1 | The outcome model, stated before any number |
| 2 | Headline, and exactly how the allocator differs from the fixed schedule |
| 3 | The same comparison, one failure cause at a time |
| 4 | Why the allocator loses on raw recoveries, and the 27-point sensitivity sweep in full |
| 5 | Whether the headline survives re-drawing the batch (10 seeds) |
| 6 | Cost per attempt at which the allocator wins on money |
| 7 | How often a stop or notify decision was right |
| 8 | What did not work |
| 9 | Limitations |
| 10 | Policy what-if: the allocator's own knobs |
| 11 | Explanation faithfulness and data validity |

Related: [architecture.md](architecture.md), [HLD.md](HLD.md),
[LLD.md](LLD.md), [errorlog.md](errorlog.md).

## 1. The outcome model, stated before any number (PRD Sec 5.1)

Every number below comes from a simulation study, not a field measurement.
Test-mode charge results are authored by us rather than observed from real
bank behavior, so that gets said up front instead of surfacing three
sections later as a caveat.

The frozen model (`eval/outcome_model.py`, seed 42, written before the
allocator's own scoring was tuned, and never imported by `pipeline/`):

| Cause | Success probability |
|---|---|
| `mandate_revoked`, `mandate_expired`, `amount_exceeds_mandate`, `afa_required` | always 0 - a retry cannot succeed by definition |
| `insufficient_funds` | Gaussian bump peaking at 0.55, centered `funding_event_day=3.0` days after failure, spread `1.5` days |
| `bank_technical` | starts at 0.8, exponential decay with `half_life=36h` |
| `unknown` | flat 0.05 |

What that supports is a narrow, defensible claim: the allocator spends a
scarce, capped budget well under this stated model of the world. It does
not support "recovers X% of real payments," and nothing below should be
read that way.

## 2. Headline

Cause mix (modelled from PRD Sec 2's published dominance ordering, not
observed - see Limitations):

| Policy | Attempts spent | Payments recovered | ₹ recovered | Attempts wasted on unrecoverable causes | Compliance violations |
|---|---|---|---|---|---|
| Fixed schedule (baseline) | 141 | 35 | ₹68,015 | 51 | 0 |
| Cause-aware allocator | **70** | 30 | ₹57,520 | **0** | 0 |

### How different the two policies are, in one table

All figures from `results_table` in `eval/results/run_20261008T100907.json`
(the percentage and per-attempt columns are arithmetic on those fields).

| Measure | Fixed schedule | Cause-aware allocator | Change |
|---|---|---|---|
| Retry attempts spent | 141 | 70 | 71 fewer (-50.4%) |
| Payments recovered (of 60) | 35 | 30 | 5 fewer (-14.3%) |
| Rupees recovered | ₹68,015 | ₹57,520 | ₹10,495 less (-15.4%) |
| Attempts wasted on causes that can never succeed | 51 | 0 | 51 fewer (-100%) |
| Compliance violations | 0 | 0 | none |
| Payments stopped or notified instead of retried | 0 | 18 | 18 more |
| Recoveries per 100 attempts | 24.8 | 42.9 | +18.0 |
| Rupees recovered per attempt | ₹482 | ₹822 | +₹339 |
| Net value at the illustrative ₹40.50 per attempt (Section 6) | ₹62,305 | ₹54,685 | about ₹7,620 less |

The allocator's 88 decisions in this run split 70 retry, 13 stop and 5
notify, so all three branches are live. At the first decision for each
payment: 42 retry (35 `insufficient_funds`, 7 `bank_technical`), 13 stop (8
`mandate_revoked`, 3 `mandate_expired`, 2 `amount_exceeds_mandate`) and 5
notify (4 `afa_required`, 1 `unknown`). Per-cause detail is in Section 3.

70 attempts against baseline's 141 - 50% fewer - and zero of them spent on
causes the frozen model says can never succeed. A mandate that's been
revoked, expired, or exceeded gets left alone entirely here, where a fixed
schedule burns all 3 attempts on it regardless.

The default parameters don't produce more raw recoveries, though (30 vs
35), and Section 4 is the diagnosis, not just an acknowledgment - it walks
through why mechanically, plus a scoring-function fix made this session
that moved the sensitivity sweep's advantage from 3/27 to 7/27 grid points (on the earlier batch; 6/27 on the current one, see Section 4).
Section 5 checks whether that 30-vs-35 gap itself is stable across seeds
or a property of this one draw (it's stable - baseline wins at all 10
seeds tried).

There's also a rupee figure worth putting on this, priced the same way the
outcome model itself is declared rather than sourced (Section 9 has the
caveat in full): at an illustrative ₹20 per retry attempt (blended
gateway/ops/support overhead for one attempted debit - nobody publishes a
real figure for this, so substitute your own number if you have one; the
arithmetic is the point, not the constant), 71 fewer attempts works out to
₹1,420 in avoided operational overhead across this 60-payment batch, or
about ₹24 per payment. 51 of those 71 attempts - about 72% of the
savings - were never going to buy a successful outcome in the first place
under the fixed schedule.

Compliance violations sit at zero for both policies, and that's asserted
programmatically against every scheduled attempt
(`pipeline.compliance.attempts_within_cap`, `is_peak_window`) rather than
just reported as a count - the dashboard's Batch Results view re-runs
these checks live against the loaded batch in the browser.

## 3. Per-cause breakdown

| Cause | n | Baseline recovery rate | Allocator recovery rate | Baseline attempts spent | Allocator attempts spent |
|---|---|---|---|---|---|
| `insufficient_funds` | 35 | 83% | 69% | 78 | 60 |
| `bank_technical` | 7 | 86% | 86% | 9 | 10 |
| `unknown` | 1 | 0% | 0% | 3 | 0 |
| `mandate_revoked` | 8 | 0% | 0% | 24 | 0 |
| `mandate_expired` | 3 | 0% | 0% | 9 | 0 |
| `amount_exceeds_mandate` | 2 | 0% | 0% | 6 | 0 |
| `afa_required` | 4 | 0% | 0% | 12 | 0 |

Change per cause (allocator minus fixed schedule), from the same fields:

| Cause | Recovered | Attempts spent |
|---|---|---|
| `insufficient_funds` | -5 (29 to 24) | -18 (78 to 60) |
| `bank_technical` | 0 (6 to 6) | +1 (9 to 10) |
| `unknown` | 0 (0 to 0) | -3 (3 to 0) |
| `mandate_revoked` | 0 | -24 (24 to 0) |
| `mandate_expired` | 0 | -9 (9 to 0) |
| `amount_exceeds_mandate` | 0 | -6 (6 to 0) |
| `afa_required` | 0 | -12 (12 to 0) |
| **Total** | **-5 (35 to 30)** | **-71 (141 to 70)** |

The pattern to notice: across the four structurally-unrecoverable causes
(17 of 60 payments), the allocator spends 0 attempts against baseline's 51
- every one of those 51 is wasted by definition under the frozen model.
The one `unknown` payment shows the caution trade-off: baseline spends 3
attempts on it and recovers nothing in this draw, while the allocator
notifies the customer and spends none. The frozen model does give `unknown`
a nonzero 5% success chance, so a different draw could have rewarded
baseline's blind retries; the allocator's notify-instead-of-guess choice
gives up that small chance on purpose. That is a real trade-off between
caution and raw count, not a bug.

On the two genuinely recoverable causes, baseline recovers at a higher
per-payment rate for `insufficient_funds` (83% vs 69%, spending 78 attempts
against the allocator's 60) and ties on `bank_technical` (86% each, with the
allocator spending 10 attempts to baseline's 9). Section 4
explains this as a timing-density effect - the allocator isn't worse at
recognizing what's recoverable, it's working from a wider, PRD-mandated
schedule that samples the relevant window less densely.

## 4. Diagnosing the loss, not just disclosing it (PRD Sec 5.2)

An earlier version of this document disclosed that the allocator loses to
baseline on raw recovery count at most sensitivity-sweep settings and left
it there. This section goes further: a mechanical check for why, not a
narrative guess.

### Is it a confidence problem?

Checked directly (`eval/sensitivity.py::_confidence_analysis`): logged
`cause_confidence` for every payment and cross-referenced it against every
sweep grid point's win/loss status. `cause_confidence` turns out to be
bimodal - 1.0 for 59 of 60 payments (an exact, deterministic match on the
error's `reason` field) and 0.0 for the 1 `unknown` payment, nothing in
between - and it's byte-identical across all 27 grid points, because
classification has no dependency on outcome-model parameters at all. The
same seeded batch gets reused at every grid point; only the success
probabilities change. Confidence can't correlate with the losses because
it never varies, which rules out low-confidence classification as the
explanation.

### It's the scoring function - and there was a real bug in it

That points at `pipeline/allocator.py`'s `_OFFSET_WEIGHTS`. Checking the
`insufficient_funds` weights against their own stated rationale ("middle
checkpoint favoured over guessing too early or waiting the full week,"
which implies symmetric caution) turned up a mismatch: the original
weights, `{24: 0.6, 72: 1.0, 168: 0.8}`, ranked 168h (96 hours from the 72h
middle checkpoint) above 24h (only 48 hours from it). A failed first
attempt's second try went to the farther offset before the closer one -
the code contradicted its own comment. This surfaced from re-reading the
stated reasoning against the numbers, before checking how it affected the
sweep at all; the fix (reweighting by actual distance from the middle
checkpoint, landing on `{24: 0.7, 72: 1.0, 168: 0.45}`) was decided on that
basis, not reverse-engineered from a result. `bank_technical`'s weights
were left as-is - its monotonic decay already matches the outcome model's
monotonic-decay shape, so there was no contradiction there to fix.

After the fix, the sensitivity sweep's advantage holds at 7 of 27 grid
points on the earlier batch (6 of 27 on the current one), up from 3/27 (both numbers come from the same, already-fixed
reproducibility bug described in the prior build-log entry, so it's a
clean before/after). Full reasoning and the exact numbers either side of
the change: `docs/build-log.md`, 2026-09-04.

### The sensitivity sweep, in full (PRD Sec 5.2)

The 60 payments and their cause mix are held fixed (seed 42). Three outcome
model parameters are varied on a 3 x 3 x 3 grid, 27 settings: when the
customer is funded (`funding_event_day` 1.5, 3.0, 5.0 days), how tightly
funding clusters around that day (`funding_event_spread_days` 0.75, 1.5,
3.0) and how fast a bank hiccup clears (`bank_technical_half_life_hours` 18,
36, 72). "Allocator >= baseline" means the allocator saved attempts and
recovered at least as many payments (`allocator_advantage_holds` in
`eval/sensitivity.py`). Source: `eval/results/sensitivity.json`.

**Headline: the allocator recovers at least as many payments at 6 of 27
settings. At all 27 it spends fewer attempts (15 to 88 fewer), wastes none on
unrecoverable causes (baseline wastes 51 at every setting) and has zero
compliance violations.**

| Funding event day | Settings | Allocator recovers >= baseline | Recovered, allocator minus baseline (range) | Attempts saved (range) |
|---|---|---|---|---|
| 1.5 | 9 | 0 | -20 to -8 | 15 to 50 |
| 3.0 | 9 | 2 | -10 to +1 | 46 to 88 |
| 5.0 | 9 | 4 | -6 to +3 | 50 to 73 |

All 6 settings where the allocator holds have a funding event at day 3.0 or
later (2 at day 3.0, 4 at day 5.0), a bank half-life of 36h or more, and a
tight or mid spread (0.75 or 1.5 days). A later funding event is where its
24h/72h/7d schedule reaches and baseline's day 1/2/3 does not. With an early
funding event (1.5 days) it loses on raw recoveries at all 9 settings, by 8
to 20 payments.

<details>
<summary>All 27 settings</summary>

| Funding day | Spread (days) | Bank half-life (h) | Baseline recovered / attempts | Allocator recovered / attempts | Recovered diff | Attempts saved | Rupees diff | Allocator >= baseline |
|---|---|---|---|---|---|---|---|---|
| 1.5 | 0.75 | 18 | 33 / 124 | 13 / 109 | -20 | 15 | Rs -46,530 | No |
| 1.5 | 0.75 | 36 | 35 / 120 | 19 / 98 | -16 | 22 | Rs -38,534 | No |
| 1.5 | 0.75 | 72 | 36 / 118 | 20 / 95 | -16 | 23 | Rs -39,334 | No |
| 1.5 | 1.5 | 18 | 37 / 122 | 22 / 89 | -15 | 33 | Rs -17,985 | No |
| 1.5 | 1.5 | 36 | 39 / 118 | 28 / 78 | -11 | 40 | Rs -9,989 | No |
| 1.5 | 1.5 | 72 | 40 / 116 | 29 / 75 | -11 | 41 | Rs -10,789 | No |
| 1.5 | 3.0 | 18 | 38 / 122 | 26 / 80 | -12 | 42 | Rs -16,788 | No |
| 1.5 | 3.0 | 36 | 40 / 118 | 32 / 69 | -8 | 49 | Rs -8,792 | No |
| 1.5 | 3.0 | 72 | 41 / 116 | 33 / 66 | -8 | 50 | Rs -9,592 | No |
| 3.0 | 0.75 | 18 | 26 / 162 | 23 / 82 | -3 | 80 | Rs -2,247 | No |
| 3.0 | 0.75 | 36 | 28 / 158 | 29 / 71 | +1 | 87 | Rs +5,749 | Yes |
| 3.0 | 0.75 | 72 | 29 / 156 | 30 / 68 | +1 | 88 | Rs +4,949 | Yes |
| 3.0 | 1.5 | 18 | 33 / 145 | 24 / 81 | -9 | 64 | Rs -18,491 | No |
| 3.0 | 1.5 | 36 | 35 / 141 | 30 / 70 | -5 | 71 | Rs -10,495 | No |
| 3.0 | 1.5 | 72 | 36 / 139 | 31 / 67 | -5 | 72 | Rs -11,295 | No |
| 3.0 | 3.0 | 18 | 37 / 124 | 27 / 78 | -10 | 46 | Rs -13,790 | No |
| 3.0 | 3.0 | 36 | 39 / 120 | 33 / 67 | -6 | 53 | Rs -5,794 | No |
| 3.0 | 3.0 | 72 | 40 / 118 | 34 / 64 | -6 | 54 | Rs -6,594 | No |
| 5.0 | 0.75 | 18 | 4 / 172 | 2 / 122 | -2 | 50 | Rs -6,398 | No |
| 5.0 | 0.75 | 36 | 6 / 168 | 8 / 111 | +2 | 57 | Rs +1,598 | Yes |
| 5.0 | 0.75 | 72 | 7 / 166 | 9 / 108 | +2 | 58 | Rs +798 | Yes |
| 5.0 | 1.5 | 18 | 20 / 166 | 19 / 101 | -1 | 65 | Rs +13,851 | No |
| 5.0 | 1.5 | 36 | 22 / 162 | 25 / 90 | +3 | 72 | Rs +21,847 | Yes |
| 5.0 | 1.5 | 72 | 23 / 160 | 26 / 87 | +3 | 73 | Rs +21,047 | Yes |
| 5.0 | 3.0 | 18 | 32 / 147 | 26 / 86 | -6 | 61 | Rs -6,694 | No |
| 5.0 | 3.0 | 36 | 34 / 143 | 32 / 75 | -2 | 68 | Rs +1,302 | No |
| 5.0 | 3.0 | 72 | 35 / 141 | 33 / 72 | -2 | 69 | Rs +502 | No |

</details>

This is the finding, not a defect to tune away: the allocator's advantage on
raw recoveries is narrow and depends on the outcome-model parameters. Its
advantage on attempts and on wasted attempts does not.

### The remaining gap is structural

Even after the fix, raw recovery count stays a near-tie or a loss at 21 of
27 settings, and no amount of reweighting closes that, because it comes
from something outside the scoring function entirely: baseline's fixed
schedule is day 1/2/3 (24h/48h/72h, three attempts inside three days),
while the allocator's schedule is the PRD's own published safe-spacing
fallback - 24h/72h/7 days (PRD Sec 2) - reaching a full week out. When a
customer gets funded early or mid-cycle, baseline's denser packing samples
the relevant part of the Gaussian more times and wins on raw count, even
though - per Section 2 - it's wasting attempts elsewhere on causes that
can never succeed. Reordering which of the 3 existing offsets gets tried
first narrows this gap; it can't close it, because the offsets themselves
are a PRD-mandated input, not something this codebase gets to tune, and
they were never touched.

### Why funding-window inference didn't close this gap either

`pipeline/funding_window.py` (Sec 7 build step 9) infers a likely funding
day from a customer's noisy debit history and is wired into the allocator.
When it was wired in (measured on the earlier batch, before the generator
was corrected) it moved the headline numbers by a few attempts and roughly
one payment - not the fix this gap needed, for two structural reasons. First, it can
only re-rank the 3 fixed offsets; it can't schedule at the actual inferred
day if that day falls between them. Second, `eval/outcome_model.py` is
population-level rather than per-customer, and was frozen (Sec 5.1) before
this stage existed, so even a perfect per-customer estimate wouldn't
change the probability the simulation draws from. One more number worth
having here (PRD Sec 5.2's confidence-fallback-rate metric): of the 35
`insufficient_funds` payments where Stage 4 actually ran, 40% (14 of 35)
had thin or inconsistent history and fell back to the same safe spacing
the allocator was already using before Stage 4 existed.

Closing this gap for real would mean letting the allocator schedule at
arbitrary inferred times instead of 3 fixed offsets, or extending the
outcome model to per-customer variation. Both are legitimate future work,
not something to patch in reaction to a sweep number that didn't move
enough.

## 5. Is the headline stable, or one lucky draw? (multi-seed check)

Every number so far comes from `seed=42`. `eval/multiseed.py` re-draws the
same 60-payment batch at 10 seeds (42, 1, 2, 3, 7, 13, 99, 137, 500, 2026 -
chosen before running, not selected after seeing results) against the
default outcome model, and reports the distribution rather than a single
number.

| | Baseline recovered | Allocator recovered | Recovery gap (baseline − allocator) |
|---|---|---|---|
| seed 42 (the headline) | 35 | 30 | 5 |
| Mean across all 10 seeds | 33.5 | 27.0 | 6.5 |
| Std. dev. across all 10 seeds | 4.63 | 3.69 | 4.08 |

**Baseline wins on raw recovery at all 10 of 10 seeds** - this isn't a
property of one unlucky draw, it's stable. If anything, seed 42's gap (5)
is smaller than the 10-seed mean (6.5), so the headline number is on the
*more flattering* side for the allocator relative to the wider sample, not
a cherry-picked worst case being hidden or a best case being shown.
Attempts-spent stays favorable throughout too: the allocator spends 63-95
attempts across all 10 seeds against baseline's 140-158, so that half of
the headline is the stable one. Per-seed detail (`eval/results/multiseed.json` and
`eval/results/multiseed_sweep.json`):

| Seed | Baseline recovered | Allocator recovered | Gap (baseline minus allocator) | Baseline attempts | Allocator attempts | Sweep: allocator >= baseline at (of 27) |
|---|---|---|---|---|---|---|
| 42 | 35 | 30 | 5 | 141 | 70 | 6 |
| 1 | 33 | 28 | 5 | 144 | 86 | 15 |
| 2 | 34 | 30 | 4 | 146 | 82 | 7 |
| 3 | 33 | 25 | 8 | 142 | 83 | 7 |
| 7 | 35 | 34 | 1 | 142 | 77 | 15 |
| 13 | 30 | 21 | 9 | 153 | 89 | 5 |
| 99 | 40 | 26 | 14 | 140 | 95 | 5 |
| 137 | 40 | 28 | 12 | 143 | 86 | 3 |
| 500 | 32 | 26 | 6 | 150 | 76 | 4 |
| 2026 | 23 | 22 | 1 | 158 | 63 | 21 |

The allocator spends fewer attempts and recovers fewer payments at every
seed. Reproduce with `python -m eval.multiseed`.

**A second, less comfortable check: is the sensitivity sweep's own
headline stable?** Section 4's "advantage holds at 7 of 27 grid points"
also comes from one seed. `eval/multiseed.py::run_multiseed_sweep()` runs
the *full* 27-point sweep at each of the same 10 seeds - 270 batch
computations - and reports how the holds-count itself moves.

| | Advantage holds at (of 27) |
|---|---|
| seed 42 (the headline) | 6 |
| Mean across all 10 seeds | 8.8 |
| Min / Max across all 10 seeds | 3 / 21 |

This is more variance than the raw-recovery check above, and it's the
honest thing to report rather than the flattering half. 6/27 is below
the 10-seed mean (8.8) - not cherry-picked - and the range is wide:
the weakest batch draw holds at only 3 of 27 settings, the strongest at 21. The direction of the finding doesn't change (the allocator's raw-
recovery advantage is real but narrow and settings-dependent under every
seed tried, never close to universal), but the exact count - "6 of 27" -
should be read as one point in a range from 3 to 21, not as a
precise, seed-independent number. Full per-seed data:
`eval/results/multiseed_sweep.json`. Reproduce with
`python -c "from eval.multiseed import run_multiseed_sweep; run_multiseed_sweep()"`
(takes over a minute - 270 batch computations, not run by the default test
suite at this size).

## 6. The breakeven: what cost per attempt makes this worth it

Section 2's headline leaves a real question unresolved: 50% fewer attempts
against 14% fewer payments recovered. Fewer attempts and fewer recoveries
are both true, and neither number by itself tells a merchant whether to
use this. `eval/economics.py` answers a narrower, more useful question
instead: **above what cost per retry attempt does the allocator's attempt
savings outweigh its lower recovery?**

Net value is recovered money minus money spent attempting
(`amount_recovered - attempts_spent * cost_per_attempt`), computed for
both policies from the same real batch numbers this whole document uses
(`run_20261008T100907`, `eval/results/economics.json`). The cost side is
never one buried number - three components are declared separately,
because none of them is authoritative and a reader should be able to
swap in their own:

| Component | Illustrative value | Why |
|---|---|---|
| Gateway/processing overhead | ₹20 / attempt | Same figure Section 2 already uses for its simpler one-sided calculation - kept consistent rather than inventing a second number. |
| Mandatory pre-debit notification (PRD Sec 2 requires one ≥24h before every attempt) | ₹0.50 / attempt | A transactional SMS/push in India typically runs a few paise to roughly a rupee - a round middle, not a quote. |
| Expected cost of customer annoyance leading to mandate revocation | 1% probability × ₹2,000 lifetime value = ₹20 / attempt | The least certain component by far - both the probability and the lifetime-value figure are guesses. A merchant with real mandate-churn data should replace both, not just the product. |
| **Total (default)** | **₹40.50 / attempt** | |

**Breakeven: ₹147.82 per attempt.** Above that cost, the allocator wins on
net value; below it, baseline wins, because the extra ₹10,495 baseline
recovers in this batch outweighs a low per-attempt cost more than the
allocator's 71 fewer attempts save. At the illustrative default of ₹40.50,
**baseline currently wins on net value** - stated plainly, not tuned away.
This is the honest form of the question: not "does the allocator win," but
"at what cost per attempt would it."

| Cost per attempt | Baseline net value | Allocator net value | Allocator wins on money |
|---|---|---|---|
| ₹5 | ₹67,310 | ₹57,170 | No |
| ₹20 (default gateway cost alone) | ₹65,195 | ₹56,120 | No |
| ₹40.50 (default, all 3 components) | ₹62,305 | ₹54,685 | No |
| ₹50 | ₹60,965 | ₹54,020 | No |
| ₹100 | ₹53,915 | ₹50,520 | No |
| **₹147.82 (breakeven)** | **₹47,172** | **₹47,173** | **Crosses here** |
| ₹150 | ₹46,865 | ₹47,020 | Yes |
| ₹200 | ₹39,815 | ₹43,520 | Yes |
| ₹300 | ₹25,715 | ₹36,520 | Yes |
| ₹500 | ₹-2,485 | ₹22,520 | Yes |

A reader can answer "should I use this?" from this table alone: estimate
your own blended cost per attempt (the annoyance-cost component is the one
most worth replacing with real data), find where it falls, read off the
winner. Reproduce with `python -m eval.economics`, or call
`eval.economics.run_economics()` with your own `AttemptCostAssumptions`.

### The breakeven surface, not a single defended number

The table above still picks one number for the two least-certain inputs
(1% revocation probability, ₹2,000 lifetime value) to get one blended
cost. Neither of those two is defensible as *the* number - nobody has
real mandate-churn data backing either. `compute_breakeven_surface()`
instead varies both across a grid and shows the region where each policy
wins, holding gateway (₹20) and notification (₹0.50) fixed since those
two are comparatively less contentious (real market rates exist for
both):

| Revocation risk per attempt ↓ / Customer lifetime value → | ₹500 | ₹1,000 | ₹2,000 | ₹5,000 | ₹10,000 |
|---|---|---|---|---|---|
| 0% | Baseline | Baseline | Baseline | Baseline | Baseline |
| 0.5% | Baseline | Baseline | Baseline | Baseline | Baseline |
| 1% | Baseline | Baseline | Baseline | Baseline | Baseline |
| 2% | Baseline | Baseline | Baseline | Baseline | **Allocator** |
| 5% | Baseline | Baseline | Baseline | **Allocator** | **Allocator** |
| 10% | Baseline | Baseline | **Allocator** | **Allocator** | **Allocator** |

The allocator only wins on money in the high-risk, high-value corner: 6 of
30 cells (20%), all requiring both a revocation risk of at least 2% per
attempt *and* a customer worth at least ₹2,000 in future recurring
revenue. Read this as a shape to check yourself against, not a verdict -
if your merchant's real numbers land in that corner (aggressive retrying
genuinely costing you customers, and those customers being valuable),
the allocator's caution is worth real money. If they don't, it mostly
isn't, at least not on this axis alone (the attempts-saved and
zero-waste-on-unrecoverable-causes benefits from Section 2 hold
regardless of where you land on this grid). Full 30-cell grid:
`eval/results/economics.json`'s `surface` key.

## 7. Stop-decision precision

Of the payments the allocator stopped or notified instead of retrying (18
of 60), 94% were genuinely unrecoverable under the frozen model. The other
6% (one payment) is an `unknown`-cause payment: the classifier couldn't place a cause,
`priors.py` conservatively chooses notify over a blind retry, and the
frozen model happens to give `unknown` a small nonzero (5%) success
chance. Same caution-vs-recovery trade-off as Section 3 - a declared
conservative default, not a misclassification.

Baseline never stops early by design (it's the naive comparator, retrying
regardless of cause), so there's no stop-decision precision to report for
it.

## 8. What did not work

- Live Razorpay S2S UPI AutoPay integration (Sec 5.0 integration tier) is
  gated behind a Razorpay Support activation this test account doesn't
  have. Customer and order creation succeed live. Of four mandate-creation
  routes tried across two sessions, two (`/payments/create/upi` and
  `/payments/create/recurring`) return a not-found rejection, which is the
  gating evidence; the other two (`/payments`, `/payments/create/ajax`)
  return 401, normal auth-rejection behavior on routes not meant for
  server-side calls and not gating evidence. An independent published
  source agrees. See `data/fixtures/README.md` for the precise breakdown,
  corrected there against the raw captured records rather than an earlier
  summary of them.
  `data/fixtures/*.json` comes from Razorpay's own published error-code
  documentation instead, labeled by provenance in `data/fixtures/README.md`.
- The allocator's first version repeated the same retry window on every
  attempt - caught by the sensitivity sweep showing implausibly good
  numbers, not by a unit test. See `docs/build-log.md`.
- The batch generator's failure times were anchored to wall-clock
  `datetime.now()` instead of a fixed reference point, despite the module
  claiming to be seeded for reproducibility - re-running the identical
  seed produced different headline numbers on different days. Fixed with
  a fixed anchor timestamp and a regression test. See `docs/build-log.md`.
- The `insufficient_funds` offset weights contradicted their own stated
  rationale - found and fixed this session, Section 4 above.
- Wiring funding-window inference into the allocator barely moved the
  numbers - Section 4. A real result worth reporting, not a failed feature
  worth hiding.
- The configured free-tier LLM model went unavailable mid-build (404,
  then a second working model returned truncated JSON from a
  reasoning-heavy response). Both failures degraded cleanly to the
  template fallback with zero pipeline impact - see `docs/build-log.md`.
- `setup.sh` had a Razorpay test credential hardcoded in plaintext,
  committed since the first scaffold commit. Found and fixed mid-build;
  see `docs/build-log.md`.
- The first synthetic generator produced data that broke the rules of the
  rails it imitates (329 first attempts inside peak windows, 83 AFA
  failures below the Rs 15,000 threshold, no mandate cap, 17 customers with
  two debits in one month). The Pandera contract caught it, every eval
  output was regenerated, and Section 11 reports the corrected result.
- The policy what-if assumed the funding-confidence threshold was a
  meaningful knob. It is not on this generator (Section 10).
- The public live-simulator API accepted any amount and any size of error
  payload, had no rate limit, and its webhook accepted unsigned calls. Found
  by a scripted load and fuzz run and fixed on 2026-10-08.
- The committed explanation-eval files (`explanation_eval_*.json`) were
  produced against an earlier run (`run_20260915T134833`) and not
  regenerated after the batch was corrected. Re-running them locally against
  the current run gives 7 of 7 (cached) and 88 of 88 (template) passing
  every check, but those re-run outputs are not what is committed (Section 11).

Every real error, with its root cause and fix, is collected in
[errorlog.md](errorlog.md).

## 9. Limitations

- **Simulation study, not a field measurement.** Every number above is
  scored against `eval/outcome_model.py`, a declared model of the world,
  not observed customer behavior. See Section 1.
- **The ₹20-per-attempt figure in Section 2, and all three cost
  components in Section 6's breakeven, are declared illustrations, not
  sourced data.** No public cost-per-retry-attempt figure exists for UPI
  AutoPay, and the customer-annoyance-to-revocation probability and
  lifetime-value figures in Section 6 are the least certain numbers in
  this entire document - the arithmetic (net value, breakeven) is what's
  meant to be reused, not any of the constants themselves.
- **Failure mix is modelled, not observed.** `eval/batch_generator.py`'s
  `CAUSE_MIX` (55% insufficient_funds, etc.) is grounded in PRD Sec 2's
  dominance ordering, not a published exact breakdown - Razorpay doesn't
  publish one.
- **Funding-window inference is probabilistic and, in this build, has a
  narrow effect** - see Section 4.
- **Small N.** 60 synthesized payments, not thousands. The sensitivity
  sweep (27 settings x 60 payments) exists precisely because a single run
  proves too little on its own.
- **Three of the seven cause fixtures are provisional** -
  `mandate_revoked`/`mandate_expired`/`amount_exceeds_mandate`'s exact
  `reason` strings are inferred rather than independently documented by
  Razorpay; see `data/fixtures/README.md`.
- **Compliance is demonstrated by scheduler logic, not live NPCI
  behavior.** Test mode doesn't enforce peak windows - this codebase's own
  assertions do (`pipeline/compliance.py`), checked in tests and re-run
  live in the dashboard.

## 10. Policy what-if: the allocator's own knobs (PRD Sec 5.2)

The sensitivity sweep (Section 4) varies the outcome model and keeps the
policy fixed. `eval/policy_whatif.py` does the reverse: the frozen outcome
model stays as it is and the allocator's two judgment calls vary - the
funding-window confidence threshold (below it Stage 4 is ignored) and the
retry spacing - over the same 10 seeds as Section 5. Source:
`eval/results/policy_whatif.json` (7 thresholds x 3 spacings = 21 points).
Means over 10 seeds, threshold 0.5 (the shipped default):

| Policy | Recovered (mean) | Rupees recovered (mean) | Attempts (mean) | Wasted attempts (mean) | Seeds matching or beating baseline |
|---|---|---|---|---|---|
| Fixed schedule | 33.5 | ₹81,862 | 145.9 | 48.3 | - |
| Allocator, published 24h / 72h / 168h (shipped) | 27.0 | ₹65,833 | 80.7 | 0 | 0 of 10 |
| Allocator, sooner 12h / 48h / 120h | 28.9 | ₹68,291 | 84.7 | 0 | 2 of 10 |
| Allocator, later 48h / 96h / 168h | 25.9 | ₹64,689 | 87.1 | 0 | 1 of 10 |

Compliance violations are 0 at all 21 points.

**The confidence threshold is not a meaningful knob on this batch
generator.** Every threshold from 0.3 to 0.88 gives identical results for
each spacing, and turning inference off entirely (1.01) moves the mean
recovered count by 0.2 or less (published spacing: 27.0 to 26.8). The reason
is in Stage 4's own output: across the 10 seeds there are 337
`insufficient_funds` payments, 131 of them with confidence exactly 0 (thin
history) and the rest between 0.8667 and 1.0. Nothing lands in between, so
no threshold in the middle changes who falls back. Stage 4 is therefore not
where the gap to the fixed schedule comes from.

**Spacing is where the movement is.** The sooner spacing recovers 1.9 more
payments on average than the published one (28.9 against 27.0) and still
trails the fixed schedule (33.5). The shipped defaults were not changed:
adopting the better-looking spacing after seeing it win under the outcome
model the allocator is graded against would be the circular tuning PRD Sec
5.1 forbids. It is reported as a finding.

## 11. Explanation faithfulness and data validity

### Stage 7 explanation checks

Stage 7 is the only place a model writes text, so `eval/explanation_eval.py`
checks it with eight deterministic rules (no model grades another model):
the copy describes the decided action, any rupee amount equals the decision's
amount, any clock time or date matches the schedule, customer messages avoid
payments vocabulary, `reasoning_plain` explains NPCI/mandate/AutoPay terms
only in brackets after the plain words, no internal identifiers leak, each
message fits one 160-character SMS, and the Hinglish copy is Hindi-English
rather than the English repeated.

- **What is committed.** `explanation_eval_template.json` and
  `explanation_eval_cached.json` name `run_20260915T134833` - an earlier
  batch - not the current frozen run. They report 91 of 91 template
  explanations passing every check and 4 of 7 cached explanations, the 3
  failures all being the stop sentence that used jargon without
  explaining it (fixed afterwards, see [errorlog.md](errorlog.md)).
- **What the current run gives.** Re-running
  `python -m eval.explanation_eval --source template` and `--source cached`
  against `run_20261008T100907` locally gives 88 of 88 and 7 of 7 passing
  every check. These re-run files were not committed, so the committed
  artifacts still describe the earlier run.
- **The cached explanations in the current run are all template fallbacks.**
  All 7 payments carrying a cached explanation have
  `generated_by = template_fallback`; no model output is in the frozen run.
  The `llm` source of the evaluation needs `LIVE_LLM=1` and was not part of
  this write-up.

### Data validity (`docs/DATA_QUALITY.md`)

No real failed-payment data exists, so realism cannot be measured. What is
checked is rule compliance: a Pandera contract over 5,000 generated events
(seed 42) against NPCI peak windows, the RBI Rs 15,000 authentication
threshold, the registered mandate cap, documented Razorpay error reasons and
one debit per billing cycle. Result: **pass, 0 failing rows on all five
checks** (`eval/results/data_contract.json`). Profile: median amount Rs
1,499, 33.4% of events carry usable debit history. Passing shows the data is
possible under the rules, not that real traffic looks like it.
