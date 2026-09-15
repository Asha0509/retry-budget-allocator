# Retry Budget Allocator

A fixed retry schedule treats a failed UPI AutoPay payment as a scheduling
problem — retry on day 1, day 2, day 3, and hope. It isn't one. NPCI caps a
merchant at exactly 3 retry attempts per mandate, never inside a peak
window, one successful debit per billing cycle. That budget doesn't renew
and it doesn't scale with how many payments fail. Three non-renewable
attempts, spent without knowing in advance which failures can even be
recovered, is a constrained allocation problem — and a fixed schedule that
ignores *why* a payment failed is the wrong tool for it.

![Landing page: thesis, headline result with its caveat, and a plain scorecard](docs/images/landing.png)
![Live Simulator, one click in](docs/images/live-simulator.png)
![Full trace: raw error payload, per-stage timings, allocator/baseline disagreement](docs/images/full-trace.png)

**[docs/video/pitch.mp4](docs/video/pitch.mp4)**
(2:57) — problem, architecture, a live demo through the dashboard, and the
honest results.

Three compliance invariants — never more than 3 attempts, never inside a
peak window, never more than one successful debit per cycle — are asserted
structurally in `pipeline/compliance.py`, checked in tests, and re-run live
against the batch in the dashboard's own browser code. That's a falsifiable
claim: "compliant" here means an assertion that fails loudly if violated,
not a label.

[![CI](https://github.com/Asha0509/retry-budget-allocator/actions/workflows/ci.yml/badge.svg)](https://github.com/Asha0509/retry-budget-allocator/actions/workflows/ci.yml)
98% test coverage on `pipeline/`, enforced in CI on every push — a weaker
signal than the invariants above, since it measures whether lines
executed, not whether the logic is correct, but it's there too.

## Why a fixed schedule gets this wrong

Razorpay's own S2S documentation is explicit: when a controlled UPI
AutoPay payment fails, there's no automatic retry — the merchant decides
what happens next. Most merchants decide once, with a schedule, not a
policy: retry on a fixed cadence regardless of cause.

That's wrong in two specific, checkable ways:

- **It spends attempts a cause can never convert.** An expired or revoked
  mandate has nothing to retry against — no amount of well-timed retrying
  fixes it. A fixed schedule burns all 3 attempts on it anyway, because it
  never asked why the payment failed in the first place.
- **It ignores timing that actually matters.** An insufficient-balance
  failure — the dominant cause, behind roughly 20 million AutoPay
  revocations a month — is recoverable, but only once the account is
  funded. Retrying blind, before that happens, wastes the attempt.

Neither failure is a scheduling bug. They're both the direct cost of
treating a small, regulated, non-renewable intervention budget as a
calendar problem instead of an allocation one.

## What this builds

A decision layer that classifies the failure cause, then chooses between
notifying the customer, retrying at a specific compliant time, or stopping
early — and records why each decision was made, not just what it was.

- **Deterministic where it should be** — cause classification is a lookup
  over the real Razorpay error object, not a model call. The failure
  taxonomy is small and fully known; a model here would add latency and a
  new failure mode for no benefit.
- **AI where it earns its place** — an LLM writes the plain-language
  reasoning and customer notification copy, and has no say in whether a
  retry happens. An API outage degrades the explanation text, never the
  decision.
- **Every scored candidate kept, not just the winner** — the allocator
  returns all candidate retry windows with their scores and rejection
  reasons, so the reasoning behind a decision is inspectable, not just its
  conclusion.

## Results

Over 60 synthesized failed payments (seed 42), the cause-aware allocator
spends 46% fewer retry attempts than a fixed day-1/2/3 schedule (74 vs 138)
and wastes zero of them on mandates that can never be recovered (the fixed
schedule wastes 42). Compliance violations: zero for either policy, and
that attempts-spent advantage holds across every point in a 27-setting
sensitivity sweep.

What it doesn't do at these parameters is recover more raw payments than
the naive schedule (29 vs 35) — and rather than just note that and move on,
`docs/RESULTS.md` Section 4 digs into why: it's not a confidence problem,
it's structural. Baseline's dense 3-day schedule out-samples the
allocator's wider, PRD-mandated 24h/72h/7d schedule whenever a customer's
funding event lands early. That gap isn't a fluke of one seed either:
re-drawn at 10 different seeds, baseline wins on raw recovery every single
time, and seed 42's gap is actually smaller than the 10-seed average — the
headline sits on the *more flattering* side, not a cherry-picked one
(Section 5).

That leaves a real question unresolved by either number alone: priced in
rupees per retry attempt (gateway cost, mandatory pre-debit notification,
and the risk-weighted cost of a customer revoking the mandate out of
annoyance — `docs/RESULTS.md` Section 6), the allocator only wins on net
money above **₹157.23 per attempt** — below that, baseline's extra
recovered revenue outweighs its higher attempt spend. Rather than defend
one guess for the two least-certain inputs (how often does aggressive
retrying actually cost a mandate, and what's a customer worth), Section 6
grids both and shows the shape: the allocator only wins on money in the
high-risk/high-customer-value corner (6 of 30 grid cells). Outside that
corner, baseline wins on net value too. That's the actual decision rule
this hands a reader, not a verdict either way.

**[docs/RESULTS.md](docs/RESULTS.md)** has the full numbers: the outcome
model (stated before any result, as it should be), the per-cause breakdown,
the multi-seed stability check, the breakeven surface, and what didn't work.

## What's real and what's simulated

Stated plainly, because the two are easy to blur and shouldn't be:

- **Real:** the pipeline itself runs live in the dashboard's Live
  Simulator tab — every stage executes against whatever payment you build
  or pick, through a small local FastAPI backend, with real per-stage
  timing. The compliance checks are real assertions, not display copy.
  Contact with Razorpay's live test API is real and ongoing: customer and
  order creation succeed against it, and 4 distinct mandate-creation
  routes tried across two sessions (`/payments/create/upi`, `/payments`,
  `/payments/create/ajax`, `/payments/create/recurring`) all return a
  real, captured rejection — evidence that headless mandate creation is
  gated behind a Razorpay Support activation this account doesn't yet
  have live, re-confirmed as recently as 2026-09-15 with fresh
  credentials. `api/razorpay_client.py` is a real, tested, opt-in client
  for this (`LIVE_RAZORPAY=1`) — not fully validated against production,
  since nothing has gotten past this gate yet. See
  `data/fixtures/README.md` for the precise breakdown of every route
  tried and what each result actually shows.
- **Simulated:** whether a scheduled retry actually succeeds is never
  observed — it's drawn from `eval/outcome_model.py`, a model this project
  authored and froze before any allocator logic was tuned, specifically so
  the comparison against it isn't circular. Every headline number (46%
  fewer attempts, 29 vs 35 recovered, the ₹157.23 breakeven) is a
  simulation study against that declared model, not a field measurement.
  The 7 cause fixtures used to build realistic error payloads are a mix of
  Razorpay's own published error-code documentation and, for 3 causes
  Razorpay doesn't document a dedicated error reason for, an inferred
  best-guess from token-lifecycle behavior — labeled by provenance in
  `data/fixtures/README.md`.

## Known gaps

Specific enough to act on, not hedged into meaninglessness:

- **The outcome model is authored, not observed, and the account needed to
  fix that isn't activated yet.** No real success/failure data backs any
  number in this repo. Closing this needs real outcome data from actual
  retry attempts, which needs the mandate-creation gate below to lift
  first. 4 distinct creation routes tried live (most recently 2026-09-15,
  with fresh credentials and an account the user believed already had
  activation) all still return the same rejection — this is a
  Razorpay-Support-conversation prerequisite now, not a code problem
  (`docs/build-log.md`, `data/fixtures/README.md`).
- **The classifier's lookup table covers what's documented, not what
  production actually sends.** A 2026-09-15 audit against Razorpay's
  complete published error-code reference closed the gap between "covers
  what was tested" and "covers everything documented" (3 more codes
  mapped, 3 more deliberately left to fall through to `unknown`/notify
  with reasoning, 5 more explicitly scoped out as mandate-creation or
  merchant-config errors, not charge-failure causes). It has not, and
  cannot yet, close the gap between "documented" and "what a real,
  activated production account would actually send" — that's blocked on
  the same activation as above.
- **A money-path input-validation audit found and fixed one real bug.**
  `attempts_used` indexed a ranked candidate list with no bounds check, so
  a negative value silently picked the worst-scored window instead of
  erroring (`docs/build-log.md`, 2026-09-14). Fixed and tested, and since
  then supplemented with property-based fuzzing (hypothesis, 1200+
  generated cases against the classifier) rather than left as a one-pass
  manual audit — but the fuzzing covers Stage 2 specifically, not every
  function on the money path, so other unvalidated inputs may still exist
  elsewhere unaudited.
- **The funding-window inference (Stage 4) has a narrow ceiling by
  design.** Even at high confidence, it can only re-rank the 3 fixed
  24h/72h/7d offsets — it can't schedule at the actually-inferred day if
  that falls between them. `docs/RESULTS.md` Section 4 has the full
  diagnosis.
- **The cost-per-attempt breakeven surface rests on illustrative grids,
  not sourced data.** No public figure exists for either axis (mandate-
  revocation risk per attempt, customer lifetime value) - the *shape* of
  where each policy wins is the useful part, not the specific ₹500-10,000
  and 0-10% ranges chosen for the grid. A merchant with real churn data
  should re-run `eval/economics.py` with their own numbers, not trust
  this grid's edges.

## Docs

- [docs/RESULTS.md](docs/RESULTS.md) — results, method, and limitations
- [docs/architecture.md](docs/architecture.md) — pipeline design and data flow
- [docs/prd.md](docs/prd.md) — full specification and verified sources
- [docs/build-log.md](docs/build-log.md) — what broke during the build and how it was fixed

## Repo layout

    pipeline/   the 7-stage decision engine (Sec 4) - classify, priors,
                funding window, allocate, decision, explain
    eval/       frozen outcome model, baseline, batch harness, sensitivity
                sweep, multi-seed check, cost-per-attempt breakeven surface
                (Sec 5) - never imported by pipeline/
    api/        FastAPI backend for the dashboard's Live Simulator tab,
                plus the opt-in live Razorpay client and webhook receiver
    dashboard/  React + Tailwind UI - a landing page, then Live Simulator,
                Story, Decision Trace, Batch Results
    data/       fixtures (Sec 5.0 provenance) and saved run artifacts
    docs/       results, architecture, build log, PRD
    tests/      one test file per pipeline/eval/api module
    scripts/    one-off live-API probes, not imported by anything else

## Setup

    bash setup.sh
    cp .env.example .env    # fill in keys
    source .venv/bin/activate
    pytest

## Dashboard

A landing page first: the thesis, the headline result with its caveat in
the same sentence, and a plain scorecard — readable in under 30 seconds
without touching anything interactive. One button from there into the full
dashboard's four tabs: a Live Simulator (opt-in live mode — calls the real
pipeline through a small local API, never the real Razorpay API), plus
Story, Decision Trace, and Batch Results, which read from a saved run
artifact: static files only, no live calls. The batch study itself stays
fixed and pre-computed either way.

    # terminal 1 - backend for the Live Simulator tab
    source .venv/bin/activate
    uvicorn api.main:app --reload --port 8000

    # terminal 2 - dashboard
    cd dashboard
    npm install
    npm run dev

The other three tabs work fine without the backend running; only Live
Simulator needs it. See [dashboard/README.md](dashboard/README.md) for how
to refresh the batch data after a new run.

## Authorship

This codebase was built by an AI coding assistant working from written
specifications, directed and reviewed by a human throughout rather than
run autonomously — every non-trivial design decision (the compliance
invariants, the outcome-model isolation rule, when to flag a gap instead
of silently building around it) was specified or checked before being
built, not generated and accepted unread.

The files where a subtle bug would be a money bug —
`pipeline/allocator.py`, `pipeline/compliance.py`, `pipeline/priors.py`,
`pipeline/classify.py`, `eval/baseline.py`, `eval/economics.py`,
`api/razorpay_client.py`, and the Pydantic validation in
`pipeline/ingest.py` — got the heaviest scrutiny of anything in the repo:
a dedicated adversarial-input audit that found and fixed a real fail-open
bug (`docs/build-log.md`, 2026-09-14: negative `attempts_used` silently
picked the worst-scored retry window instead of erroring), later
supplemented with property-based fuzzing (1200+ generated cases against
the classifier, not just the hand-picked ones), and a documented-error-code
audit against Razorpay's own published reference rather than working from
memory. That review is real and repeatable — the regression tests and
fuzz properties it produced are in `tests/`, not just the fixes.

`CLAUDE.md`, kept in the repo rather than deleted once the build finished,
is the actual record of what the assistant was and wasn't permitted to
decide on its own: hard constraints that could not be silently reinterpreted,
claims that were checked against Sec 2's sources and banned once found
false or overstated, and the standing instruction to flag a conflict or a
gap explicitly rather than build the disallowed thing quietly. It's a
record of judgment calls made during the build, not a boilerplate config
file.
