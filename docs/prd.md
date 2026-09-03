# PRD — Recurring Payment Recovery: Retry Budget Allocator
### Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery
### v1.0 — Verified, build-ready

**Author:** Asha Jyothi Boddu
**Last updated:** September 2026
**Status:** Research complete. All load-bearing claims verified against primary sources. Ready to build.

---

## 0. Track 3 requirements, verbatim — the acceptance test

From razorpay.com/buildathon:

> **AI Revenue Recovery** — Find revenue that's slipping away and win it back.
> Build an agent that detects revenue at risk, determines the right intervention, and executes a bounded recovery workflow: from payment failures and checkout abandonment to overdue receivables.
> Example directions: Payment degradation → root cause → recovery action, Checkout drop-off recovery, **Failed-subscription recovery**, B2B receivables chaser, **Mandate retry sequencer**, Hinglish voice recovery, Promise-to-pay tracker.
> **The bar:** Don't just identify the problem. Show **measured money recovered across a batch**, with **compliant escalation**, **stopping rules**, and an **audit trail**.

Evaluated on: Problem Taste, Build Quality, AI Judgment (using AI appropriately, opting for deterministic solutions where AI is unnecessary), Failure Recovery.

Submission: public GitHub repo + 5-minute pitch video + architecture documentation. No deployment requirement.

---

## 1. Problem statement

When a UPI AutoPay recurring payment fails, Razorpay's controlled flow returns retry responsibility to the merchant. Their own S2S documentation states: *"We will not attempt any retry if the debit fails for tokens with the notification object in the created order. You should manually retry the debit attempt."*

The merchant must then decide how to spend a hard budget of three NPCI-permitted retry attempts, restricted to non-peak windows, with only one successful debit allowed per billing cycle.

That budget is usually spent on a fixed schedule that ignores why the payment failed. An expired or revoked mandate consumes attempts it can never convert. An insufficient-balance failure — the dominant cause, driving roughly 20 million AutoPay revocations a month — consumes all three attempts within days, before the customer's account is funded again.

**This is a constrained allocation problem, not a scheduling one:** a small, regulated, non-renewable budget of interventions, spent without knowing which failures are recoverable. This project builds the decision layer that classifies the failure cause, chooses between notifying, retrying at a specific compliant time, or stopping early, and records why each decision was made.

---

## 2. Verified facts and constraints

Every claim below traces to a primary or published source. Nothing inferred.

| Fact | Source |
|---|---|
| Razorpay does not auto-retry in the controlled UPI AutoPay flow; merchant must retry manually | Razorpay S2S recurring-payments docs |
| NPCI cap: 1 original attempt + max 3 retries per mandate | NPCI circular, effective 31 July 2025 |
| Non-peak windows only; peak = 10:00–13:00 and 17:00–21:30 | NPCI circular |
| Non-compliance risk: restrictions on UPI API access, penalties, suspension of new customer onboarding | NPCI circular |
| Only one successful debit per token per billing cycle | Razorpay docs |
| Pre-debit notification required ≥24h before every debit | NPCI operating guidelines / RBI |
| ~20 million AutoPay revocations per month, driven by insufficient balance | NPCI data via Business Standard |
| UPI AutoPay failure rate 8–15%, vs 2–3% for card mandates | Published industry analysis |
| Spaced retry windows (24h / 72h / 7d) recover 15–20% of failed payments | Published industry analysis |

**Explicitly NOT claimed:**
- Not claiming Razorpay's managed Subscriptions T+3 retry is "blind" — that is a different product surface and conflating the two is a factual error.
- Not claiming retry spacing is novel — 24/72/168h spacing is published best practice, and Stripe ships ML-driven retries. The novel part is narrow: cause-classified allocation of a hard-capped budget with an explicit stop decision.
- Not claiming the system *knows* payday. It infers a likely funding window from the customer's prior successful debit dates plus a salary-credit prior, with a confidence score.

---

## 3. What we are building

An agent that, for each failed recurring payment, decides how to spend a scarce, regulated intervention budget.

**Intervention set (three real branches, all exercised):**
1. **Notify** — send/advance a pre-debit notification; used when the cause is likely fixable by the customer with warning.
2. **Retry at time T** — spend one attempt, scheduled into a compliant non-peak window at a time chosen by cause and inferred funding likelihood.
3. **Stop** — spend nothing; escalate to a customer action. Used when retry cannot succeed (expired mandate, revoked mandate, amount exceeds mandate cap).

A system whose only action is "retry later" is a scheduler, not an intervention-chooser, and would weaken the match to the track's "determines the right intervention". All three branches must be live.

**Scope (v1):** UPI AutoPay recurring debits, single merchant, Razorpay test-mode API. Card e-mandates and NACH documented as extension, not built.

---

## 4. Architecture

**Stage 1 — Ingestion.** Consume failed-payment events (webhook or test-mode charge failure). Input: payment id, token id, amount, error object, mandate metadata, attempt history.

**Stage 2 — Cause classification (deterministic).** Map the real Razorpay error object (`code`, `description`, `source`, `step`, `reason`) to a cause class:
```
FailureCause = insufficient_funds | mandate_revoked | mandate_expired
             | amount_exceeds_mandate | afa_required | bank_technical | unknown
```
Deterministic lookup, not an LLM call. This is the "opt for deterministic where AI is unnecessary" decision, and it should be stated explicitly in the pitch.

**Stage 3 — Recoverability prior.** Each cause carries a recoverability score and a recommended action shape, grounded in Section 2's published data. `mandate_revoked` → 0.0, stop. `insufficient_funds` → recoverable, timing-sensitive. `bank_technical` → recoverable, short-horizon.

**Stage 4 — Funding-window inference (for insufficient_funds only).** From the customer's prior successful debit dates plus a salary-credit prior, estimate a likely funding window with a confidence. **If confidence < threshold, fall back to documented safe spacing (24h / 72h / 7d) rather than a speculative date.** This fallback is a designed feature, not a limitation to hide.

**Stage 5 — Budget allocation.** Given attempts remaining (of 3), choose: spend now, hold for a better window, or stop. Never exceed the cap. Never schedule inside a peak window.

**Stage 6 — Decision record.**
```
RecoveryDecision {
  payment_id, token_id, amount
  cause: FailureCause
  cause_confidence: float
  recoverable: bool
  action: notify | retry | stop
  scheduled_at: datetime | null
  window_compliant: bool
  attempts_used: int, attempts_remaining: int
  reasoning_plain: str      # human-readable, compliance-officer legible
  reasoning_technical: str  # error code, priors, confidence
}
```

**Stage 7 — LLM layer (narrow, and only here).** Generate the plain-language `reasoning_plain` string and the customer-facing notification copy (including Hinglish, which Track 3 lists as a direction). The LLM never decides whether to retry. Free-tier model via `.env` (Kimi K2.6/K3 or GLM-4.7-Flash), swappable if rate-limited.

---

## 5. Evaluation

**Batch:** N failed payments (target 50+). Failure mix modelled on published rates (insufficient_funds dominant, per Section 2) — **stated openly as modelled, not observed.**

### 5.0 How the batch is actually produced — a feasibility constraint

Each UPI AutoPay mandate requires a registration authorisation flow before any debit can be attempted against it. Producing 50+ mandates end-to-end through test mode is slow and may consume a disproportionate share of a short build window. Discovering this on build day would be expensive.

**Two-tier approach, disclosed in the write-up:**

1. **Integration tier (small, real).** A handful of mandates registered and charged end-to-end through Razorpay test mode, with real error objects captured from real API responses. This proves the integration is genuine and gives you authentic payloads. Record these responses to `data/fixtures/` and use them as the schema source of truth.
2. **Batch tier (large, replayed).** The evaluation batch is generated locally as events conforming exactly to the captured fixtures' schema — same field names, same error codes, same shapes. The pipeline cannot tell the difference, because the contract is identical.

**Say this plainly in the results write-up and the video.** "A few cases run against the live test API; the batch replays that exact schema at volume" is an honest, ordinary engineering decision that a reviewer will recognise as sensible. Claiming 50 live end-to-end mandates when the batch was generated locally would not be.

If the end-to-end registration flow proves quicker than expected, raise the integration-tier count — but do not let it block the eval harness, which is the artifact that produces your submission numbers.

**Baseline:** fixed-schedule, cause-agnostic retry (attempt on day 1, 2, 3). This is a non-arbitrary comparator representing what a merchant building the retry logic themselves would most likely do first.

### 5.1 The outcome model — declaring it, not hiding it

In Razorpay test mode the charge result is chosen by the caller. If the allocator schedules a retry and we then mark it successful, we have authored the result. Left unaddressed, "money recovered" is circular: it measures our assumptions, not the system's judgment.

**Mitigation — separate the outcome model from the decision system, and declare it up front:**

Define a fixed, stated success model before any allocator code runs, and never let the allocator see it:
- `insufficient_funds` — success probability rises after a customer's funding event and decays with distance from it
- `bank_technical` — high short-horizon success probability, decaying over days
- `mandate_revoked`, `mandate_expired`, `amount_exceeds_mandate` — success probability zero at all times
- `afa_required` — success only with customer action, never by silent retry

Fix the model with a seed, publish it in the results write-up, and evaluate the allocator against it. This makes the exercise an honestly-labelled **simulation study**: it measures whether the allocator spends a scarce budget well *given a stated model of the world*, not whether it recovers real money from real banks. That claim is defensible; the stronger one is not.

### 5.2 Sensitivity analysis — the thing that makes the result mean something

A single run against one outcome model proves little, because the model was chosen by the same person as the allocator. Re-run the batch across a range of plausible parameter settings — funding events early vs. late in the cycle, tighter vs. looser clustering, higher vs. lower technical-failure recovery speed — and report how the allocator's advantage over the baseline changes.

If the advantage holds across the range, the result is robust. **If it only appears under one favourable setting, say so** — that is a genuine, publishable finding about when cause-aware allocation helps and when it doesn't, and reporting it honestly is worth more than a single flattering number. This section is the strongest available answer to the AI Judgment and honest-metrics criteria.

**Results table:**

| Policy | Attempts spent | Payments recovered | ₹ recovered | Attempts wasted on unrecoverable causes | Compliance violations |
|---|---|---|---|---|---|
| Fixed schedule (baseline) | | | | | |
| Cause-aware allocator | | | | | |

**Secondary metrics:**
- Recovery rate per cause class (where the system helps most, and where it doesn't)
- Stop-decision precision: of payments we refused to retry, how many would genuinely never have succeeded
- Attempts saved: budget preserved by not spending on unrecoverable causes
- Confidence-fallback rate: how often funding inference was too uncertain and safe spacing was used instead

**Honesty section, required in the results write-up:** failure mix is modelled; funding inference is probabilistic; test-mode outcomes are controlled rather than observed from real customer behaviour; N is small.

---

## 6. Output and presentation

Three views. Plain language leads; technical detail sits underneath.

**View 1 — Story.** One payment's journey, jargon-free, understandable by someone with no payments knowledge. Payment failed, account empty, three tries allowed, salary due Friday, here's how the budget was spent, here's the outcome.

**View 2 — Decision trace.** Per payment, each step as a sentence: what the bank said → whether that's fixable → how many tries remain → when to spend one and why → outcome. Raw error code and confidence in small text alongside.

**View 3 — Batch results.** The table above, framed as economics rather than accuracy.

### 6.1 Making technical depth visible

Plain-language framing must not make the system look like a frontend with nothing behind it. The following are requirements, not polish — each one surfaces reasoning work that a mockup cannot fabricate.

- **Show rejected alternatives.** Every retry decision displays the candidate windows the allocator evaluated, each with its score and the reason it was or wasn't chosen — including windows rejected for peak-hour non-compliance. A view showing what was considered and discarded is unmistakably a decision system rather than a display.
- **Show the expected-value arithmetic.** Surface `attempts_remaining` and `P(success at T)` with real numbers, not just the resulting choice.
- **Put the sensitivity sweep (Sec 5.2) on screen.** A chart of allocator advantage across outcome-model parameters is the most technical artifact this project produces and cannot be faked. It also visibly demonstrates awareness of the result's own fragility.
- **Run the compliance invariants live.** A panel that executes the real assertions against the batch — attempts never exceeded 3, zero peak-window schedules, one successful debit per cycle — and shows them passing. Verification performed on screen, not asserted in prose.
- **Keep the raw error object visible** beside its plain-English translation, so a technical viewer can confirm the classification parsed a real payload rather than matching a hardcoded string.
- **Make the pipeline itself visible.** The decision trace must be rendered as the seven named stages from Sec 4 — ingest, classify, prior, funding window, allocate, record, explain — each showing its actual input, output, and elapsed time for the selected payment. Stages that were skipped (funding-window inference is not run for `mandate_revoked`) show as skipped with the reason. This turns the architecture diagram from a doc artifact into something the viewer watches execute, and it demonstrates that the system is a structured pipeline rather than one function behind a UI.

Plain language is the entry point, not the ceiling: every view should let a non-technical viewer understand the outcome and a technical viewer verify the mechanism.

### 6.2 Demo reliability

"Execution reliability" is part of the Build Quality criterion, and a demo that stalls on camera is the most avoidable way to lose it. Free-tier LLM endpoints rate-limit; APIs hiccup.

- **The dashboard runs from saved run artifacts by default**, not live API calls. Batch results are written to `data/runs/<timestamp>.json` and the dashboard reads from there, so the demo replays a completed run deterministically.
- **The LLM explanation layer caches to disk.** Once a decision's plain-language reasoning is generated, it is stored with the run. A provider outage during recording degrades nothing, because nothing is regenerated live.
- **A live mode exists but is opt-in**, for showing the real integration when the network cooperates. Never the default path for a recording.

### 6.3 Architecture documentation (judged deliverable)

`docs/architecture.md` is one of the three submitted artifacts and needs its own spec, not an afterthought at the end of the build:

- Mermaid diagram of the seven pipeline stages with their data contracts
- Where the deterministic/LLM boundary sits, and the reasoning for it
- The compliance invariants and where they are enforced in code
- Data provenance: the integration tier vs. replayed batch split (Sec 5.0)
- The outcome model and its isolation from the allocator (Sec 5.1)
- Known limitations, restated rather than buried in the PRD

### 6.4 `docs/RESULTS.md` — required artifact

Raw output in `eval/results/` has no narrative wrapper, and a judge should not have to assemble the story from JSON. One file, written the way a paper's results section reads, linked prominently from the README:

1. **Headline** — money recovered vs. baseline, attempts saved, compliance violations (zero)
2. **The outcome model, stated up front** (Sec 5.1) — before any number, so nothing looks like a concealed assumption
3. **Per-cause breakdown** — where the allocator helps, and where it makes no difference
4. **Sensitivity sweep** (Sec 5.2) — how the advantage holds across parameter settings, reported honestly if it narrows
5. **Stop-decision precision** — of the payments refused a retry, how many would genuinely never have converted
6. **What did not work** — failure modes found, cases the system handles poorly
7. **Limitations** — simulation study, modelled failure mix, probabilistic funding inference, small N

Written so a non-specialist follows the headline and a technical reader can audit the method. This is where the evaluation criteria are demonstrated by evidence rather than announced.

### 6.5 Documentation site — optional, gated

A rendered docs site (MkDocs Material, ~30 minutes) gives a linkable URL for the application form. **Build order step 13, gated on steps 1–12 being complete.** GitHub already renders `docs/` browsably with Mermaid support, so the marginal gain is presentation only. A polished site over an unfinished engine signals misplaced effort — never start it before the eval harness has produced real numbers.

### 6.6 `/logs/` — raw runtime logs, distinct from the build log

`docs/build-log.md` is a curated narrative for the pitch — a handful of real stories, written after the fact. `/logs/` is different: every pipeline run writes structured, timestamped, machine-readable entries (JSONL) as it executes — stage entered, stage completed, error caught, retry classification made, fallback triggered. This is what actually gets mined to write the build log and the RESULTS.md "what did not work" section, rather than relying on memory of what happened three days ago.

Git-ignore the bulk of `/logs/` (it's large and regenerable), but commit a **small representative sample** — one run's worth, or the run that produced a real caught error — so a judge or interviewer can see raw evidence, not just a narrative claim about it.

### 6.7 Required flowcharts (in `docs/architecture.md`)

Mermaid, rendered natively by GitHub, no external tool needed. Three diagrams minimum, each answering a different question:

1. **Pipeline flowchart** — the seven stages (Sec 4) as boxes, data contracts on the edges, the deterministic/LLM boundary visually marked (e.g., a colour or shape distinction between Stage 2/3/5/6 and Stage 7).
2. **Decision flowchart** — the actual branching logic inside the allocator: cause classified → recoverable? → confidence check → notify / retry-at-T / stop. This is the diagram a non-technical reviewer should be able to follow without reading code.
3. **State diagram** — a mandate's lifecycle across its budget: `active (3 attempts left)` → attempt outcomes → `active (2 left)` → ... → `recovered` or `exhausted`. Makes the "bounded" and "stopping rules" requirements visually literal.

A flowchart that isn't kept in sync with the code is worse than none — regenerate or hand-check these when Stage logic changes, don't write them once at the start and forget them.

Optional if time permits: replay mode — a "run batch" control that steps through cases live, so the demo reads as a working system rather than a screenshot.

---

## 7. Repository structure and build order

```
/pipeline/
  ingest.py           # Stage 1
  classify.py          # Stage 2 (deterministic)
  priors.py            # Stage 3
  funding_window.py    # Stage 4
  allocator.py         # Stage 5 — core logic
  decision.py          # Stage 6 record
  explain.py           # Stage 7 (LLM, narrow)
/eval/
  harness.py           # Section 5
  baseline.py          # fixed-schedule comparator
  results/
/dashboard/            # three views, built last
/data/
  fixtures/            # real error objects captured from test mode (Sec 5.0)
  runs/                # batch runs, decision logs (git-ignored)
/docs/
  prd.md
  architecture.md      # Mermaid, Sec 6.3
  RESULTS.md           # narrative results, Sec 6.4
  build-log.md         # curated narrative: what broke and how it was fixed
/logs/
  *.jsonl              # raw runtime logs - every pipeline run, structured,
                        # git-ignored except a small committed sample (Sec 6.6)
/.github/workflows/ci.yml
```

**Build order:**
1. Cause classification + recoverability priors (deterministic core — everything depends on it)
2. Compliance invariant tests (never >3 attempts, never in peak window, one debit per cycle) — replaces the scaffold placeholder test
3. Capture real error-object fixtures from test mode (Sec 5.0, integration tier) — do this early, before the batch generator is written, so the generated events match a verified schema rather than a guessed one
4. Allocator with budget and window constraints
5. Outcome model (Sec 5.1) — written and frozen BEFORE the allocator is tuned, kept in a separate module the allocator never imports
6. Baseline comparator
7. Batch runner + eval harness → **this produces the submission numbers**
8. Sensitivity sweep (Sec 5.2) across outcome-model parameters
9. Funding-window inference with confidence fallback
10. LLM explanation layer
11. Dashboard, three views
12. `docs/RESULTS.md` (Sec 6.4), `docs/architecture.md` (Sec 6.3), pitch video, failure-recovery narrative
13. (Optional, gated on 1–12) Rendered documentation site (Sec 6.5)

**Build log:** keep a running note of what actually breaks. Track 3's evaluation includes Failure Recovery as its own axis; this cannot be reconstructed from memory at the end.

---

## 8. Risks and honest limitations

- **Funding-window inference is probabilistic.** Present with confidence; fall back to documented spacing when uncertain. Overstating this is the most likely way to be picked apart in a demo.
- **Failure mix is modelled, not observed.** Ground it in published rates and say so.
- **Results are a simulation study, not a field measurement.** Test-mode outcomes are authored, so the honest claim is "the allocator spends a scarce budget well under a stated, published outcome model", never "this recovers X% of real payments". Section 5.1 and 5.2 exist to make this rigorous rather than apologetic.
- **Compliance is demonstrated by scheduler logic, not live NPCI behaviour.** Test mode does not enforce peak windows; your code does.
- **Two of Track 3's example directions point here** — expect other submissions in this space. Differentiation is the budget-allocation framing and evaluation honesty, not topic novelty.
- **Retry timing is not the largest lever** — pre-debit notification quality matters more. This is why `notify` is a first-class intervention, not an afterthought.
- **Free-tier LLM reliability** — `.env`-driven model swap is the mitigation; the LLM is off the critical path by design, so an outage degrades explanations, not decisions.

---

*End of PRD v1.0.*
