# Retry Budget Allocator

**Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery**

[![CI](https://github.com/Asha0509/retry-budget-allocator/actions/workflows/ci.yml/badge.svg)](https://github.com/Asha0509/retry-budget-allocator/actions/workflows/ci.yml)
98% test coverage (264 tests, `pytest --cov=pipeline`) — enforced in CI on every push, not just claimed here.

## The problem

When a UPI AutoPay recurring payment fails, Razorpay's controlled flow returns
retry responsibility to the merchant — its own S2S documentation states that no
automatic retry is attempted and the merchant should retry manually.

The merchant must then decide how to spend a hard budget of **three
NPCI-permitted retry attempts**, restricted to non-peak windows, with only one
successful debit allowed per billing cycle.

That budget is usually spent on a fixed schedule that ignores *why* the payment
failed. An expired or revoked mandate consumes attempts it can never convert. An
insufficient-balance failure — the dominant cause, behind roughly 20 million
AutoPay revocations a month — consumes all three attempts within days, before the
customer's account is funded again.

This is a **constrained allocation problem, not a scheduling one**: a small,
regulated, non-renewable budget of interventions, spent without knowing which
failures are recoverable.

## What this builds

A decision layer that classifies the failure cause, chooses between notifying,
retrying at a specific compliant time, or stopping early, and records why each
decision was made.

- **Deterministic where it should be** — cause classification is a lookup over
  the real Razorpay error object, not a model call
- **AI where it earns its place** — an LLM writes the plain-language reasoning
  and customer notification copy, and never decides whether to retry
- **Compliance proven, not claimed** — invariants (max 3 attempts, no peak-window
  scheduling, one debit per cycle) are asserted in tests and re-run live

## Results

Over 60 synthesized failed payments (seed 42), the cause-aware allocator spends
**45% fewer retry attempts** than a fixed day-1/2/3 schedule (76 vs 138) and
wastes **zero** on mandates that can never be recovered (vs 42 for the fixed
schedule) — with zero compliance violations for either policy, asserted
programmatically, and that attempts-spent advantage holds at every point in a
27-setting sensitivity sweep. It does **not** recover more raw payments than the
naive schedule at these parameters (29 vs 35) — reported honestly, with the
sweep showing exactly when and why, rather than only the favorable case.

**[docs/RESULTS.md](docs/RESULTS.md)** — full headline numbers, the outcome
model (stated before any number), per-cause breakdown, the sensitivity sweep,
and what did not work. This is a simulation study against a declared, published
outcome model, not a field measurement.

## Docs

- [docs/RESULTS.md](docs/RESULTS.md) — results, method, and limitations
- [docs/architecture.md](docs/architecture.md) — pipeline design and data flow
- [docs/prd.md](docs/prd.md) — full specification and verified sources
- [docs/build-log.md](docs/build-log.md) — what broke during the build and how it was fixed

## Setup

    bash setup.sh
    cp .env.example .env    # fill in keys
    source .venv/bin/activate
    pytest

## Dashboard

Three views (Story, Decision Trace, Batch Results) over a saved run
artifact - reads static files only, no live API calls (PRD Sec 6.2).

    cd dashboard
    npm install
    npm run dev

See [dashboard/README.md](dashboard/README.md) for how to refresh the data
after a new batch run.
