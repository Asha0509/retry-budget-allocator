# Pitch video script (5 minutes)

A beat sheet, not a word-for-word transcript: timing, what's on screen, and
the exact commands/clicks for each beat. Recording itself is the one
submission artifact this session couldn't produce directly - this gets as
close to that as writing can.

Before recording: start both servers (`uvicorn api.main:app --port 8000` and
`cd dashboard && npm run dev`), open http://localhost:5173, and have
`docs/RESULTS.md` open in a second tab/window to jump to if needed.

---

## 0:00-0:25 - Hook + problem (screen: README, or slides)

> "When a UPI AutoPay payment fails, Razorpay's own docs say the merchant
> has to retry it manually - there's no auto-retry. NPCI gives you exactly
> 3 tries, never during peak hours, one success per cycle. Most merchants
> spend that budget on a fixed schedule - day 1, day 2, day 3 - regardless
> of *why* the payment failed. An expired mandate gets 3 attempts it can
> never convert. This is a constrained allocation problem, not a scheduling
> one, and this project is the decision layer that spends that budget on
> purpose."

Show: README's problem section, or say it over a slide. Keep it under 25s -
this is context, not the pitch.

## 0:25-1:10 - What was built (screen: architecture.md's pipeline diagram)

> "Seven stages. Classify the failure cause first - a deterministic lookup
> over the real Razorpay error object, never a model call, because the
> cause taxonomy is fully known and a model would only add latency and a
> new failure mode. Score recoverability. Infer a funding window with a
> confidence, falling back to documented safe spacing when unsure. Allocate
> the budget across three real branches - notify, retry at a chosen
> compliant time, or stop early. Only the very last stage touches an LLM,
> to write the plain-language explanation, and it never influences the
> decision itself."

Show: the Mermaid pipeline diagram in `docs/architecture.md`, briefly.

## 1:10-2:30 - Live demo (screen: Live Simulator tab) - the core of the video

The section that proves this is real, not a mockup. Three clicks:

1. **Click Karan, click Run this payment.** While it runs: "This is calling
   the actual Python pipeline right now, through a small local API - no
   canned recording behind it." When it finishes: "Karan's payment needs
   additional authentication above the RBI threshold. A fixed schedule
   would just retry blindly, and that can't work here - AFA needs the
   customer to act, not another debit attempt. The allocator correctly
   notifies instead." Point at the disagreement banner and the real
   per-stage timings, especially the Explain stage's real (often
   several-second) LLM latency - "that's a live API call, and if it fails,
   watch what happens" (only say this if a fallback has actually fired in
   rehearsal - otherwise skip the aside).
2. **Switch to Try your own, paste garbage JSON**, e.g.
   `{"code":"X","reason":"totally_made_up","description":"gibberish"}`,
   click Run. "This is what happens when the classifier genuinely can't
   place a payload - it says so. Confidence zero, routed to notify, not a
   forced guess." Probably the strongest moment in the demo - invite the
   viewer to try to break it themselves.
3. **Click into "This payment, full trace"** on either result. "Every
   candidate time slot the allocator considered is here, not just the
   winner - including the ones it rejected for landing in a peak window -
   alongside the frozen model's own probability estimate for each, shown
   for comparison only and never fed back into the decision."

## 2:30-3:40 - The honest result (screen: Batch Results tab)

> "60 synthesized payments, real Razorpay error schemas, a frozen and
> declared outcome model the allocator never sees. The allocator spends 46%
> fewer attempts than a fixed schedule and wastes zero of them on mandates
> that could never succeed - the baseline wastes 42."

Point at the live compliance panel: "These three invariants - never over 3
attempts, never in a peak window, one success per cycle - are being checked
against this batch right now, live in the browser, not just claimed in a
doc."

> "Here's the part most submissions skip: on raw recovery count, the
> allocator does not beat the fixed schedule most of the time. A 27-point
> sensitivity sweep only favors it at 7 of 27 settings." Show the chart.
> "We didn't stop at disclosing that, we dug into why. Confidence turned
> out to be invariant across every setting, which ruled it out as the
> cause - so we went back into the scoring function itself and found a
> real contradiction in our own offset weights. Fixed it, wrote down the
> reasoning before rerunning anything, and the result moved from 3 of 27 to
> 7 of 27. Earned, not cherry-picked."

## 3:40-4:25 - Failure recovery (screen: docs/build-log.md, scroll)

> "This log is pulled from what actually happened, not written up from
> memory afterward. A few examples: we tried registering live UPI AutoPay
> mandates against Razorpay's test API and hit a wall - S2S UPI turned out
> to be gated behind a support-activated flag we don't have, confirmed with
> four separate probes rather than a guessed wrong endpoint. We caught our
> own allocator repeating the identical retry window on every attempt - the
> sensitivity sweep's numbers were too good to be true, and that's what
> gave it away. And a batch generator that was supposed to be reproducible
> wasn't, because it anchored to wall-clock time instead of a fixed seed -
> caught when the exact same command gave two different answers an hour
> apart."

## 4:25-5:00 - Close

> "None of this claims to recover real money - it's a simulation study
> against a declared outcome model, stated up front before every number,
> because test-mode results are ours to author and pretending otherwise
> would be dishonest. What it does show: a cause-aware budget allocator
> that spends a hard-capped, regulated resource deliberately, proves its
> own compliance live on screen, and states plainly when its advantage
> holds and when it doesn't. Repo's public, results and the full build log
> are in the README."

---

## If something breaks during recording

- **LLM call fails or is slow on camera:** fine, maybe better - point at
  it. "That's the fallback firing live - the explanation degrades, the
  decision doesn't." Don't panic-retry live; let it fall back and narrate
  it.
- **Backend not running / Live Simulator shows the red error box:** the
  other three tabs still work off committed data - fall back to walking
  through Story/Decision Trace/Batch Results instead of the live tab if
  the API process died mid-recording.
- **Batch Results numbers look different from this script:** they're
  pulled from `docs/RESULTS.md` as of when this was written. If the batch
  has been regenerated since, read whatever's actually on screen instead
  of forcing the numbers above - the shape of the story (fewer attempts,
  zero waste, an honest sensitivity result) is what matters, not the exact
  digits.
