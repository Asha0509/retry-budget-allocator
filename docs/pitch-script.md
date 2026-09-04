# Pitch video script (5 minutes)

Not a transcript to read word-for-word - a beat sheet with timing, what's on
screen, and the exact commands/clicks for each beat. Recording is the one
submission artifact this session couldn't produce directly; this closes as
much of that gap as possible in writing.

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

> "Seven stages. Classify the failure cause - deterministic, a lookup over
> the real Razorpay error object, never a model call, because the cause
> taxonomy is fully known and a model would only add latency and a new
> failure mode. Score recoverability. Infer a funding window with a
> confidence, falling back to documented safe spacing when unsure. Allocate
> the budget across three real branches - notify, retry at a chosen
> compliant time, or stop early. Only the very last stage touches an LLM,
> to write the plain-language explanation - and it never influences the
> decision itself."

Show: the Mermaid pipeline diagram in `docs/architecture.md`, briefly.

## 1:10-2:30 - Live demo (screen: Live Simulator tab) - the core of the video

This is the section that proves it's real, not a mockup. Three clicks:

1. **Click Karan, click Run this payment.** While it runs: "This is calling
   the actual Python pipeline right now, through a small local API - not a
   canned recording." When it finishes: "Karan's payment needs additional
   authentication above the RBI threshold. A fixed schedule would just
   retry blindly - that can't work, AFA needs the customer to act. The
   allocator correctly notifies instead." Point at the disagreement banner
   and the real per-stage timings, especially the Explain stage's real
   (often several-second) LLM latency - "that's a real API call, and if it
   fails, watch what happens" (only say this if you've seen a fallback
   fire in rehearsal - otherwise skip the aside).
2. **Switch to Try your own, paste garbage JSON**, e.g.
   `{"code":"X","reason":"totally_made_up","description":"gibberish"}`,
   click Run. "This is what happens when the classifier genuinely can't
   place a payload - it says so. Confidence zero, routed to notify, not a
   forced guess." This is the strongest single moment in the demo -
   invite the viewer to try to break it themselves.
3. **Click into "This payment, full trace"** on either result. "Every
   candidate time slot the allocator considered, not just the winner -
   including ones it rejected for landing in a peak window - and here's
   the frozen model's own probability estimate for each, shown only for
   comparison, never fed back into the decision."

## 2:30-3:40 - The honest result (screen: Batch Results tab)

> "60 synthesized payments, real Razorpay error schemas, a frozen and
> declared outcome model the allocator never sees. The allocator spends 46%
> fewer attempts than a fixed schedule, and wastes zero of them on mandates
> that could never succeed - baseline wastes 42."

Point at the live compliance panel: "These three invariants - never over 3
attempts, never in a peak window, one success per cycle - are executed
against this batch right now, in the browser, not just claimed."

> "Here's the part most submissions won't show you: on raw recovery count,
> the allocator does NOT beat the fixed schedule most of the time - a
> 27-point sensitivity sweep only holds in the allocator's favor at 7 of
> 27 settings." Show the chart. "We didn't stop at disclosing that. We
> diagnosed it: confidence turned out to be invariant across every setting,
> which ruled it out - so we reviewed the scoring function itself and found
> a real internal contradiction in our own offset weights. Fixed it,
> documented the reasoning before re-running anything, and the result moved
> from 3 of 27 to 7 of 27 - honestly, not by picking a friendlier number."

## 3:40-4:25 - Failure recovery (screen: docs/build-log.md, scroll)

> "This log is real, not reconstructed after the fact. A few examples: we
> tried to register live UPI AutoPay mandates against Razorpay's test API
> and hit a wall - S2S UPI is gated behind a support-activated flag we
> don't have, confirmed with four separate probes, not a guessed wrong
> endpoint. We caught our own allocator repeating the identical retry
> window on every attempt - the sensitivity sweep's numbers were too good
> to be true, and that's what gave it away. And a batch generator that
> claimed to be reproducible actually wasn't, because it anchored to
> wall-clock time instead of a fixed seed - found because the exact same
> command gave two different answers an hour apart."

## 4:25-5:00 - Close

> "This isn't a claim that it recovers real money - it's a simulation study
> against a declared outcome model, stated plainly before every number,
> exactly because test-mode results are ours to author and claiming
> otherwise would be dishonest. What it does show: a cause-aware budget
> allocator that spends a hard-capped, regulated resource deliberately
> instead of blindly, proves its own compliance live, and is honest about
> exactly when its advantage holds and when it doesn't. Repo's public,
> results and the full build log are in the README."

---

## If something breaks during recording

- **LLM call fails or is slow on camera:** this is fine, arguably better -
  point at it. "That's the fallback firing live - the explanation degrades,
  the decision doesn't change." Do not panic-retry live; let it fall back
  and narrate it.
- **Backend not running / Live Simulator shows the red error box:** the
  other three tabs still work off committed data - fall back to walking
  through Story/Decision Trace/Batch Results instead of the live tab if
  the API process died mid-recording.
- **Batch Results numbers look different from this script:** they're pulled
  from `docs/RESULTS.md` at the time this was written - if the batch was
  regenerated since, use whatever's actually on screen and don't force the
  exact numbers above; the shape of the story (fewer attempts, zero waste,
  honest sensitivity result) is what matters, not the literal digits.
