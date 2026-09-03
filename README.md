# Retry Budget Allocator

**Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery**

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

**[docs/RESULTS.md](docs/RESULTS.md)** — headline numbers, method, sensitivity
analysis, and what did not work. Results are a simulation study against a
published outcome model, not a field measurement; the model is stated before any
number.

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

## Dashboard (build order step 11)

    bash setup.sh --dashboard
    cd dashboard && npm run dev
