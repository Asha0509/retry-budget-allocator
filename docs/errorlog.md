# Error log

Every real error, wrong assumption and near miss from building this project:
what broke, how it was detected, the root cause, the fix and the lesson. Only
events with evidence are listed; the evidence is named in each entry.

How this relates to the other records: [build-log.md](build-log.md) is the
dated narrative written as things happened and is the primary source here;
this file re-organises it with the same fields for every event and adds the
events that exist only in git history (marked "git history") or in the
documentation pass that produced this file. Raw runtime evidence lives under
`logs/` (git-ignored in bulk). Results context: [RESULTS.md](RESULTS.md).
Design context: [HLD.md](HLD.md), [LLD.md](LLD.md).

Dating note: the date is the one recorded in the build log. The git history was
re-dated, so commit dates (2026-09-03 to 2026-09-18) do not always agree with
build-log dates (some entries are dated 2026-10-07 and 2026-10-08). Where an
event has no build-log entry the commit date is used and marked. Figures quoted
inside an entry are the figures at the time; the current numbers are in
[RESULTS.md](RESULTS.md).

## Index

| ID | Date | Area | What broke (short) |
|---|---|---|---|
| E01 | 2026-09-03 | Secrets | Malformed `.env` line; key fragments echoed to a terminal |
| E02 | 2026-09-03 | Integration | Razorpay mandate registration gated for the test account |
| E03 | 2026-09-03 | Allocator | Later attempts re-selected the window that had just failed |
| E04 | 2026-09-03 | Funding window | Inference barely moved the results (wrong assumption) |
| E05 | 2026-09-03 | Stage 7 | Free-tier model removed, then a second model truncated its reply |
| E06 | 2026-09-03 | Secrets | Real test credentials hardcoded in `setup.sh` since the first commit |
| E07 | 2026-09-03 | Evaluation | "Seeded" batch changed between runs (wall-clock anchor) |
| E08 | 2026-09-04 | Allocator | Offset weights contradicted their own stated rationale |
| E09 | 2026-09-04 | Dashboard | Live Simulator banner contradicted itself; two tabs with one label |
| E10 | 2026-09-04 | API (git history) | Live API accepted nonsense input; frontend mis-rendered validation errors |
| E11 | 2026-09-04 | Tooling | Dev servers served stale code on the WSL `/mnt/c` filesystem |
| E12 | 2026-09-14 | Compliance | Negative `attempts_used` silently chose the worst window (fail-open) |
| E13 | 2026-09-14 | Secrets | Redaction command missed a line; full API key printed |
| E14 | 2026-09-14 | Integration | No network in the sandbox; earlier gating claim overstated |
| E15 | 2026-09-15 | Integration | Fresh credentials and a new route: still gated |
| E16 | 2026-09-15 | Classifier | Audit found documented error codes missing from the lookup |
| E17 | 2026-09-15 | Dashboard | Hook-order violation; the stale-server problem recurred |
| E18 | 2026-09-15 | Evaluation | Multi-seed sweep overwrote the canonical `sensitivity.json` |
| E19 | 2026-09-15 | Compliance | Third invariant existed but nothing enforced it; wrong stop sentence |
| E20 | 2026-09-04 to 2026-09-18 | Docs (git history) | Counts, section numbers and file names drifted from the code |
| E21 | 2026-10-07 | Stage 7 | Stop explanation used unexplained jargon |
| E22 | 2026-10-07 | Policy study | The confidence threshold was assumed to matter; it does not |
| E23 | 2026-10-08 | Data | Synthetic batch broke the rules of the rails it imitates |
| E24 | 2026-10-08 | API security | Public API: no caps, no rate limit, unsigned webhook |
| E25 | 2026-09-18 (git history) | CI | Security-scorecard action image pull started failing |
| E26 | 2026-09-18 (git history) | Tests | Mutation testing found untested compliance boundaries |
| E27 | 2026-10-08 | Docs | Drift found while writing the design docs |

## Entries

### E01 - Malformed `.env`; key fragments printed (2026-09-03)

- **What broke.** `.env` had a malformed, duplicated `LLM_API_KEY` line (missing
  `=`). A shell `grep` plus `source` used to read Razorpay keys for a manual API
  test printed key fragments into terminal output.
- **How detected.** `python-dotenv` warned about the malformed line, and the
  fragments were visible in the command's own output.
- **Root cause.** Loading secrets through the shell instead of Python, on top of
  a `.env` template bug (see E06).
- **Fix.** Stopped using shell `source` or `grep` on `.env`; credentials are now
  read only inside Python via `python-dotenv` and never printed. The exposure was
  reported to the key owner immediately so the key could be rotated.
- **Lesson.** Never touch secret files from the shell. This became a standing
  rule in the engineering constraints file.
- **Evidence.** build-log 2026-09-03 (row 1).

### E02 - Razorpay UPI AutoPay mandate registration is gated (2026-09-03)

- **What broke.** Every probe of the server-to-server mandate-creation route for
  UPI AutoPay returned `400 BAD_REQUEST_ERROR - "The requested URL was not found
  on the server."`, even for a plain non-recurring collect payment. Customer and
  order creation worked on the same account.
- **How detected.** `scripts/capture_fixtures.py` against the live test API, then
  targeted probes to rule out a wrong endpoint. An independent published source
  says UPI recurring via Collect/Intent needs activation by Razorpay Support.
- **Root cause.** Account-level gating, the feasibility risk PRD Sec 5.0 named in
  advance. Not a code defect.
- **Fix.** Did not request activation (out of scope for the build window). Kept
  the captured evidence (`data/fixtures/_capture_attempts.json`) and built the
  seven cause fixtures from Razorpay's published error documentation, each
  labelled documented, provisional or live. The evaluation is a simulation study
  and says so.
- **Lesson.** Plan the evaluation so it does not depend on the gated integration,
  and label provenance on every fixture.
- **Evidence.** build-log 2026-09-03 (row 2); `data/fixtures/README.md`.

### E03 - Later attempts re-selected the window that had just failed (2026-09-03)

- **What broke.** `allocate()` scored the same three offsets from the original
  failure time regardless of `attempts_used`, so attempt 2 chose the same
  highest-scoring window as attempt 1.
- **How detected.** The sensitivity sweep, not a unit test: at an early funding
  event (day 1.5) the allocator recovered fewer payments than the fixed schedule
  at 9 of 9 grid points, which was implausibly bad for a design meant to be
  smarter. The baseline's day 1/2/3 spread really did probe three different
  times.
- **Root cause.** Candidate generation does not depend on `attempts_used`, and
  the pick always took the single top score.
- **Fix.** Rank all compliant candidates by score and index the ranking with
  `attempts_used`. Added `test_successive_attempts_pick_distinct_windows_not_the_same_one_again`
  and `test_attempt_order_follows_descending_score`. After the fix the advantage
  held at 6 of 27 points, down from a buggy 17 of 27. Offset weights and the
  published spacing were left alone rather than retuned to chase a better number.
- **Lesson.** A result that looks too good or too bad is a bug report. Sweeps
  find defects that unit tests written by the same author do not.
- **Evidence.** build-log 2026-09-03 (row 3); commit fd4976a.

### E04 - Funding-window inference barely moved the results (2026-09-03)

- **What broke.** Not a defect: a wrong expectation. Stage 4 was expected to close
  the early and mid funding-event gap the sweep exposed. It did not: allocator
  attempts went 77 to 74, recoveries 31 to 30, sweep advantage 6 to 7 of 27 (at
  the time).
- **How detected.** Running the full batch and sweep before and after wiring it
  in and diffing, as the build plan instructed.
- **Root cause.** Two structural limits. The candidate set is still three fixed
  offsets, so an estimate can only re-rank them, not place a retry at the inferred
  day. And the frozen outcome model is population-level, so even a perfect
  per-customer estimate does not change the success probability the simulation
  draws from.
- **Fix.** None to the code or the outcome model: adding a fourth offset or
  editing the model to manufacture a better number would be the circular tuning
  PRD Sec 5.1 forbids. Documented as a limitation and measured further in E22.
- **Lesson.** Report a feature that does not pay off. Do not edit the yardstick.
- **Evidence.** build-log 2026-09-03 (row 4); RESULTS.md Section 4.

### E05 - Free-tier model removed, then a second model truncated (2026-09-03)

- **What broke.** The configured `EXPLANATION_MODEL` was no longer on the
  free tier (live call: 404, the provider suggested a paid slug). After switching
  to a genuinely free model, its reply came back empty: the model spent 240 of the
  400 allowed tokens on its own reasoning before reaching the JSON answer.
- **How detected.** The first failure on the single manual live smoke test, which
  the mocked unit tests deliberately do not cover. The second by dumping the whole
  response object and finding `native_finish_reason: "length"`.
- **Root cause.** A moving free-tier catalogue; a reasoning model with too small a
  token budget.
- **Fix.** Did not take the paid slug (forbidden by the constraints). Queried the
  provider's model list for current `:free` models and picked one that returned
  well-formed content, changed via `.env` with no code change. Raised `max_tokens`
  from 400 to 1000, and added an explicit empty-content check with a clear message.
- **Lesson.** Both failures landed on the template fallback with no pipeline
  impact, which confirmed that keeping the model off the critical path works under
  real provider flakiness, not only in mocks.
- **Evidence.** build-log 2026-09-03 (row 5); commit 9d1aa50.

### E06 - Real test credentials hardcoded in `setup.sh` (2026-09-03)

- **What broke.** `setup.sh` embedded the actual Razorpay test key id and secret
  in the `.env.example` text it generates, committed since the first scaffold
  commit and publicly visible. The same template lacked an `=` on the
  `LLM_API_KEY` line, the likely root cause of E01. The `.env.example` file itself
  had never been committed, so the documented `cp .env.example .env` step did not
  work on a fresh clone.
- **How detected.** Reading `setup.sh` while writing documentation.
- **Root cause.** A bootstrap script that inlined real values.
- **Fix.** Swept the repository for other exposure first (exact values plus
  `rzp_test_` and `sk-or-v1-` patterns; none found). Replaced the values with
  placeholders, fixed the missing `=`, and committed `.env.example`. Rotating the
  test key was chosen over rewriting public history: a rotated key makes the old
  value in history harmless.
- **Lesson.** Grep for every secret-shaped string before the first public commit;
  a template is code.
- **Evidence.** build-log 2026-09-03 (row 6); commit 637e84c.

### E07 - The "seeded" batch changed between runs (2026-09-03)

- **What broke.** `generate_batch` anchored failure times to `datetime.now(IST)`.
  Re-running the sweep with the same seed and `n` held the advantage at 7 of 27
  points, then 6 of 27 an hour later.
- **How detected.** The headline changed between two runs of the same command.
- **Root cause.** The seeded RNG controlled relative offsets only. The wall-clock
  anchor shifted each event's time of day, which flips peak-window classification
  of some candidates.
- **Fix.** A fixed `_BATCH_ANCHOR_TIME`. Added a regression test that generates the
  batch twice with a real 1.1 s sleep between calls and asserts identical failure
  times (the earlier reproducibility test ran both calls microseconds apart and
  rarely crossed a peak boundary). Re-ran everything and corrected the documents.
- **Lesson.** A reproducibility test must vary the thing that could break
  reproducibility, here time.
- **Evidence.** build-log 2026-09-03 (row 7); commit 6bad66b.

### E08 - Offset weights contradicted their own rationale (2026-09-04)

- **What broke.** The code comment said the 72h middle checkpoint is favoured and
  caution is symmetric around it, but the `insufficient_funds` weights
  `{24: 0.6, 72: 1.0, 168: 0.8}` ranked 168h (96 h from the middle) above 24h
  (48 h away). A failed first attempt's second try went to the farther window.
- **How detected.** Re-reading the comment against the numbers during a diagnosis of
  why the allocator loses on raw recoveries (`_confidence_analysis` first ruled out
  classification confidence, which is 1.0 for 59 of 60 payments and 0.0 for the
  other, identical at every grid point).
- **Root cause.** A hand-authored heuristic that did not match its stated logic.
- **Fix.** Reweighted by distance from the checkpoint to `{24: 0.7, 72: 1.0, 168: 0.45}`.
  The reasoning was written and reviewed before re-running the sweep so the change
  could not be curve-fitted. The sweep advantage went from 3 to 7 of 27 (on the
  batch of the time). `bank_technical` weights were unchanged: monotonic decay
  already matched the outcome model's shape, so there was no contradiction.
- **Lesson.** Decide a fix on the reasoning, then measure it. The remaining gap
  turned out to be structural (RESULTS.md Section 4).
- **Evidence.** build-log 2026-09-04 (row 8); commits 0cb4e8c, ae1e644.

### E09 - Live Simulator banner contradicted itself (2026-09-04)

- **What broke.** For the Priya scenario the banner read "allocator chose retry,
  baseline chose retry" under a headline saying they disagree. Both did choose
  retry; only the time differed. Separately, two buttons were labelled "Decision
  Trace" at once (the outer tab and the simulator's inner tab), and a browser test
  script clicked the wrong one.
- **How detected.** Driving the real browser flow with Playwright and reading the
  screenshots, not by reading code. The case needed an action match with a time
  mismatch, which only that live run produced.
- **Root cause.** The backend's `decisions_differ` correctly ORs action and time
  differences, but the frontend showed one "disagree on action" message for both.
- **Fix.** Two messages (action differs; same action, different time) and renamed
  the inner tabs to "This payment, as a story" and "This payment, full trace". Re-ran
  the flow with zero console errors.
- **Lesson.** Look at the rendered result; copy that is technically true can still
  read as a contradiction.
- **Evidence.** build-log 2026-09-04 (row 9); commit 2be8188.

### E10 - Live API accepted nonsense; frontend mis-rendered validation errors (2026-09-04, git history)

- **What broke.** The first `SimulateRequest` had no bounds: any `amount`
  (including zero or negative), any `attempts_used`, any day of month. Once bounded,
  the frontend mishandled the error shape: FastAPI returns an array of `{loc, msg}`
  objects in `detail` for a 422 while the app's own errors put a string there, and the
  old client passed `detail` straight to `new Error(...)` (which would print as
  `[object Object]`; inferred from the old code).
- **How detected.** While exercising the Live Simulator (commit messages 9f04445 and
  4550a2c; the exact trigger is not recorded beyond that).
- **Root cause.** Optional fields typed as bare `int`; the client assumed one error
  shape.
- **Fix.** `Field` constraints (`amount` > 0, `attempts_used` 0-3,
  `prior_debit_day_of_month` 1-28, `n_prior_debits` 0-24) with tests, and a client
  that formats both the string and the array shape. The larger gap this exposed was
  closed on 2026-10-08 (E24).
- **Lesson.** Validate at the boundary the first time, and handle every error shape
  the server can send.
- **Evidence.** commits 9f04445, 4550a2c.

### E11 - Dev servers served stale code (2026-09-04)

- **What broke.** A recorded walkthrough showed the Hinglish notification text hours
  after the line had been deleted and committed. `curl` of the served module showed
  the old code.
- **How detected.** Inspecting the recording frame by frame. Unit tests import
  modules fresh each run and cannot see a long-lived server.
- **Root cause.** `npm run dev` and `uvicorn --reload` had been running for hours on
  `/mnt/c` (a Windows drive under WSL2), where file-change notifications do not
  reliably cross the boundary, so neither watcher saw the edits, silently.
- **Fix.** Restarted both and verified with a fresh `curl` of the served file before
  re-recording.
- **Lesson.** A running dev server is not proof it serves current code. After any edit
  to `dashboard/src` or `api/`, restart and `curl` for the change. Promoted to a
  standing rule after it recurred (E17).
- **Evidence.** build-log 2026-09-04 (row 18); commit ca5a13f.

### E12 - Negative `attempts_used` chose the worst window (fail-open) (2026-09-14)

- **What broke.** `allocate()` indexed a ranked list with `attempts_used` and never
  validated it. `-1` did not error: it reported `attempts_remaining=4` (breaking the
  "never more than 3" bookkeeping) and, through Python's negative index, picked the
  last, worst-scored 168h window. `baseline_decide()` had the same pattern, and
  `FailedPaymentEvent.amount` accepted a negative value despite the docstring
  promising loud failure at the boundary.
- **How detected.** A deliberate audit of malformed input, reproduced with a script
  before writing any fix. No test failed: existing tests covered only values at or
  above the cap, which a `max(..., 0)` clamp happened to make safe. That asymmetry
  hid the bug.
- **Root cause.** The predicate `attempts_within_cap` existed and the harness used it
  after the fact, but the decision functions never called it.
- **Fix.** Guard at the top of `allocate()` and `baseline_decide()` raising
  `ValueError`; `Field(gt=0)` on `amount` and `Field(ge=0, le=3)` on `attempts_used`.
  Updated one test whose premise no longer held, split it into a boundary test and a
  fail-loud regression test, and added matching tests for the baseline and ingestion.
  16 new tests, 295 passing at the time, coverage unchanged at 98%.
- **Lesson.** On a money path, an out-of-range input must fail loudly, never produce a
  plausible-looking answer. Test both sides of every bound. The property-based tests
  added later cover this class (4,300+ generated cases passed at the time).
- **Evidence.** build-log 2026-09-14 (row 19); commit be3f9eb.

### E13 - Redaction command missed a line; full key printed (2026-09-14)

- **What broke.** While checking `.env` for an unrelated reason, a `sed` command meant
  to mask secret values missed one line because that line was malformed: a stray
  duplicate `LLM_API_KEY` entry from the same root cause as E01 (a "commented
  fallback" block whose lines had no `#`). The full key printed unmasked.
- **How detected.** Immediately, in the command's output.
- **Root cause.** Inspecting a secrets file with a redaction filter that depends on the
  file being well-formed.
- **Fix.** Repaired the line and commented out the duplicate block with a line-anchored
  edit that never printed the value. Reported it at once and recommended rotating the
  key. `.env` is git-ignored, so no history rewrite was needed.
- **Lesson.** Redaction by pattern is not safe on a file you do not trust; read single
  values in Python only.
- **Evidence.** build-log 2026-09-14 (row 20).

### E14 - No network in the sandbox; an earlier gating claim was overstated (2026-09-14)

- **What broke.** A live re-verification attempt failed with
  `httpx.ConnectError: Temporary failure in name resolution`: the sandbox had no
  egress. Re-reading the raw captures then showed the docs claimed a consistent 400
  across three payment-creation probes when only one (`/payments/create/upi`) got
  that rejection; the other two returned `401 Authentication failed`.
- **How detected.** The connection error itself; then re-examining
  `data/fixtures/_capture_attempts.json` against the prose summary of it.
- **Root cause.** A prose summary written from memory instead of from the raw record.
- **Fix.** No result was invented. Corrected `data/fixtures/README.md` and RESULTS.md
  against the raw JSON: a 401 means the route exists and rejects server-side Basic
  Auth, which is not evidence of gating. The finding survived on its real, narrower
  evidence. Asked for a re-run from a networked machine.
- **Lesson.** Summarise from the artifact, not from the previous summary. State the
  environment's limits instead of working around them with a plausible result.
- **Evidence.** build-log 2026-09-14 (row 21); commit 37c8d27.

### E15 - Fresh credentials and a new route: still gated (2026-09-15)

- **What broke.** With fresh test credentials and an activation email reportedly on
  the account, `POST /payments/create/recurring` (never tried before) returned the
  same not-found rejection, with both Razorpay's documented success and failure test
  VPAs. Customer and order-with-token creation succeeded live.
- **How detected.** `scripts/live_mandate_probe.py` with `LIVE_RAZORPAY=1`, saving
  every raw response (`data/fixtures/_live_mandate_probe.json`).
- **Root cause.** Not established. Either activation had not propagated to this key or
  the flow differs; it cannot be told apart from here.
- **Fix.** Did not treat the email as proof; tested directly. Fed the bare SDK error
  through `classify_cause`, which correctly returns `unknown` (confidence 0.0) and so
  notify. Four creation routes had now been tried across two sessions: two return the
  not-found rejection (`/payments/create/upi`, `/payments/create/recurring`) and two
  return 401, which is not gating evidence. The next step is a conversation with
  Razorpay Support, not another endpoint guess.
- **Lesson.** Test the claim on the exact key and route in question.
- **Evidence.** build-log 2026-09-15 (row 22); commit 33fcff6.

### E16 - Classifier coverage audit (2026-09-15)

- **What broke.** Nothing failed; an audit against Razorpay's full published error
  list found four documented UPI codes and several mandate codes missing from the
  lookup.
- **How detected.** Deliberate cross-check against the pages fetched fresh.
- **Root cause.** The table covered "what was tested", not "everything documented".
- **Fix.** Mapped `payment_collect_request_expired` and `vpa_resolution_failed` to
  `bank_technical` and `reqauth_mandate_not_acknowledged` to `afa_required`. Left
  `invalid_vpa`, `payment_cancelled` and `funds_blocked_by_mandate` unmapped on
  purpose (they fall to `unknown` and notify, the conservative default). Excluded
  mandate-registration failures and a merchant-configuration error from the taxonomy
  as a scope boundary. 6 new tests.
- **Lesson.** Coverage of the documented set is checkable; coverage of what production
  sends is not, and stays open until the integration is unlocked.
- **Evidence.** build-log 2026-09-15 (row 23); commit eff20bc.

### E17 - Hook-order violation; stale server again (2026-09-15)

- **What broke.** In the landing-page redesign an early `return` for the landing page
  sat before a `useMemo` call, breaking React's Rules of Hooks. Separately a class
  added to `LandingPage.jsx` did not appear on the running dev server: E11 again.
- **How detected.** The hook issue by re-reading the component against the rules
  before running it (React does not always throw immediately). The stale server by
  `curl`ing the served module and grepping for the new class.
- **Root cause.** The early return placed above a hook; the same `/mnt/c` watcher gap.
- **Fix.** Moved the early return below every hook; restarted the server and re-checked
  with `curl` before screenshots. Promoted the stale-server lesson into the standing
  constraints because two occurrences make a pattern.
- **Lesson.** "Documented once" is not "checked every time".
- **Evidence.** build-log 2026-09-15 (row 24); commits f1d17ff, 4732690.

### E18 - Multi-seed sweep overwrote the canonical `sensitivity.json` (2026-09-15)

- **What broke.** `run_sweep()` wrote `eval/results/sensitivity.json` on every call, so
  looping it over 10 seeds silently replaced the committed seed-42 file with whichever
  seed ran last (it briefly held seed 2026's data).
- **How detected.** Noticed before commit, on a committed result file that nothing
  should have touched (the commit message does not name the command).
- **Root cause.** A side effect inside a function reused as a library call.
- **Fix.** Added `write_output=False` to `run_sweep()` for `run_multiseed_sweep()`,
  restored the canonical file, and added a test that writes a marker into the canonical
  path and asserts the multi-seed sweep never touches it.
- **Lesson.** Check the diff for files you did not mean to change.
- **Evidence.** commit 2875e44 (git history); `tests/test_multiseed.py`.
- **A finding from the same pass** (not an error): the sweep's own headline varies far
  more across seeds than the raw-recovery gap; this was added to RESULTS.md Section 5
  as found.

### E19 - The third compliance invariant was not enforced (2026-09-15)

- **What broke.** `at_most_one_success_per_cycle()` and
  `FailedPaymentEvent.billing_cycle_successes` existed and were unit-tested in
  isolation, but no decision path read them. The dashboard honestly marked that row
  "enforced by construction", which made the gap easy to miss.
- **How detected.** A grep audit for anything that claimed to be checked but was not.
  No test caught it; each only exercised the function alone.
- **Root cause.** Scaffolding added for a constraint but never wired in.
- **Fix.** `allocate()` and `baseline_decide()` take `billing_cycle_successes`, validate
  it and return `stop` ahead of every other branch. The field flows through
  `AllocatorDecision` and `RecoveryDecision`. A fifth scenario, Meera, makes the refusal
  visible live. The dashboard's third check became a real computation. Verifying Meera
  live exposed a second bug: the generic stop sentence says the customer must set up a
  new mandate, which is wrong when a debit already succeeded; fixed with a dedicated
  sentence in both `decision.py` and `explain.py`. 25 new tests including two
  property-based; 363 passing at the time. Batch numbers unchanged (no synthetic event
  starts mid-cycle).
- **Lesson.** Search for claimed-but-unchecked guarantees. Verify a new path through the
  running system, not only in tests.
- **Evidence.** build-log 2026-09-15 (row 26); commit efa4e98.

### E20 - Counts, section numbers and file names drifted (git history)

- **What broke.** Repeatedly, documents fell behind the code: a stale test count
  (f1e6dae, 2026-09-04); `architecture.md` pointing at a RESULTS section number that
  moved after renumbering, a live client never documented, "4 independent probes"
  instead of the corrected "4 routes across two sessions" (7bc0436, 2026-09-15);
  `eval/economics.py` and its test pointing at a run file that had been replaced, plus
  five screenshots that predated the compliance work and showed a stale test count and
  the old "enforced by construction" row (4b56f09, 2026-09-15); test counts again after
  the API hardening (de9844a, 2026-09-18).
- **How detected.** Documentation audits and cross-checks of every doc-to-doc section
  reference.
- **Root cause.** Numbers and names copied into prose by hand.
- **Fix.** Corrected in place and regenerated the screenshots. See E27 for the next
  round.
- **Lesson.** Anything that is a number, a path or a section number is a candidate for
  generation or for a check.
- **Evidence.** commits f1e6dae, 7bc0436, 4b56f09, de9844a.

### E21 - The stop explanation used unexplained jargon (2026-10-07)

- **What broke.** The deterministic stop explanation said the payment "cannot succeed
  without the customer setting up a new mandate": exactly the unexplained jargon the
  presentation rule forbids. It shipped in every stop decision and in three cached
  explanations of the frozen run.
- **How detected.** The first run of the Stage 7 faithfulness eval
  (`jargon_explained` check): 83 of 91 template explanations passed every check and all
  8 failures were that sentence; 4 of 7 cached explanations passed. No earlier test
  caught it because tests asserted what the sentence said, not how.
- **Root cause.** Wording written for engineers, with no automated check of the
  presentation rule.
- **Fix.** Plain words first, term in brackets: "...until the customer sets up their
  automatic payment again (a new mandate)." Template source went to 91 of 91. A
  parametrised test now requires every template explanation to pass every check. The
  cached explanations in the committed eval artifacts still carry the old wording
  because they belong to an earlier run (see E27).
- **Lesson.** Make a stated rule executable.
- **Evidence.** build-log 2026-10-07 (row 27); commits 5786854, f7bcbd9.

### E22 - The confidence threshold was assumed to matter (2026-10-07)

- **What broke.** A wrong assumption, not a bug: the policy what-if was planned around
  the funding-window confidence threshold being a meaningful knob. Every threshold from
  0.3 to 0.88 gave identical results.
- **How detected.** The first full grid run: the recovered-payments column was constant
  down every threshold. A wiring bug was ruled out by counting Stage 4 fallbacks per
  threshold, then printing the raw confidence values: at the time 123 of 335
  `insufficient_funds` payments scored exactly 0.0 and the other 212 sat between 0.87
  and 1.0. On the corrected batch the saved file reports 131 of 337 and a non-zero range
  of 0.8667 to 1.0.
- **Root cause.** Stage 4's confidence is close to binary here: fewer than three
  observations give 0, three or more consistent ones give 0.87 or higher (formula in
  LLD.md Section 3.6).
- **Fix.** Reported as a finding. The grid was made denser above 0.85, the result file
  carries the confidence distribution, and the defaults were not changed. A better
  spacing (12h/48h/120h) exists under the outcome model, but adopting it after seeing
  it win against the model the allocator is graded on would be circular tuning.
- **Lesson.** Look at the distribution of an input before building a study around
  varying it.
- **Evidence.** build-log 2026-10-07 (row 28); `eval/results/policy_whatif.json`;
  commit 8483515.

### E23 - The synthetic batch broke the rules of the rails it imitates (2026-10-08)

- **What broke.** A Pandera contract written from the published rules failed the old
  generator: 329 first attempts inside NPCI peak windows, 83 AFA failures below the Rs
  15,000 threshold, no mandate cap on any event, and 17 customers with two debits in
  one month (from stepping back a fixed 30 days per month).
- **How detected.** The contract run over 5,000 events, instead of eyeballing a few rows.
- **Root cause.** A generator that never encoded the rules it was meant to respect.
- **Fix.** Off-peak failure times, round-rupee price points with AFA events above Rs
  15,000, a mandate cap per event, calendar-month debit history. Every eval output was
  regenerated (70 vs 141 attempts, 30 vs 35 recovered, breakeven Rs 147.82) and the
  contract now passes with 0 failing rows on all five checks. Passing shows the data is
  possible under the rules, not that real traffic looks like it
  ([DATA_QUALITY.md](DATA_QUALITY.md)).
- **Lesson.** If realism cannot be measured, rule compliance still can.
- **Evidence.** build-log 2026-10-08 (row 29); commits c55b121, 9346015, 7603be4.

### E24 - The public API had no input caps, rate limit or webhook signature (2026-10-08)

- **What broke.** The deployed API accepted any `amount` and any size of `raw_error`,
  had no rate limit on `/api/simulate`, and the webhook returned 200 to unsigned
  requests and appended them to a log file on disk.
- **How detected.** A scripted fuzz and load run against the deployed service, not a
  failing test.
- **Root cause.** Demo-time shortcuts (the webhook was documented as "deliberately no
  signature verification") left in place when the service became publicly reachable;
  validation had only checked that `amount` was positive.
- **Fix.** `amount` capped at Rs 10 lakh (100,000,000 paise); `raw_error` capped at
  16,384 bytes; a sliding one-minute per-client limit (default 30 calls, 429 beyond);
  the webhook requires an HMAC-SHA256 signature under `RAZORPAY_WEBHOOK_SECRET`, with
  503 when no secret is set, 401 for a bad signature and 413 for a body over 65,536
  bytes. Tests: `test_simulate_rejects_absurd_inputs`, `test_simulate_is_rate_limited`,
  `test_webhook_closed_without_secret`, `test_webhook_rejects_bad_signature_and_oversize`.
- **Remaining limits.** The limiter keys on the first `X-Forwarded-For` entry and keeps
  its state in process memory (per worker, reset on restart); see HLD.md Section 8.
- **Lesson.** A shortcut that is safe on localhost is a vulnerability on a public host;
  close it before the endpoint is reachable.
- **Evidence.** build-log 2026-10-08 (row 30); commits 26264a2, de9844a.

### E25 - The security-scorecard action stopped working (2026-09-18, git history)

- **What broke.** Per the commit message, the OpenSSF Scorecard workflow's `gcr.io`
  image pull started failing.
- **How detected.** CI (the commit message is the only record).
- **Root cause.** The pinned action version (v2.4.0) depended on an image pull that no
  longer worked; the commit does not say more.
- **Fix.** Upgraded `ossf/scorecard-action` from v2.4.0 to v2.4.4. Separately, Dependabot
  was regrouped to monthly, grouped updates (commit eb94bd6).
- **Lesson.** Pinned third-party actions rot; keep an updater on them.
- **Evidence.** commits ae1b0f3, eb94bd6.

### E26 - Mutation testing found untested compliance boundaries (2026-09-18, git history)

- **What broke.** The compliance tests passed but did not pin every boundary: the README
  records that mutation testing of `pipeline/compliance.py` found nine untested boundary
  changes.
- **How detected.** `mutmut` over the compliance module. Passing tests only show that
  lines ran, not that the assertions bite.
- **Root cause.** Boundary conditions (start-inclusive and end-exclusive peak windows,
  cap edges, microsecond clearing) not asserted at the exact edges.
- **Fix.** Added boundary tests in `tests/test_compliance.py`. The README reports 31 of
  32 mutants now killed, the survivor being an equivalent mutant; the weekly workflow
  tolerates at most that one. The mutation counts come from the README and the workflow
  and were not re-run for this document.
- **Lesson.** Mutation-test the claims most likely to be challenged.
- **Evidence.** commit 320ab0a; `.github/workflows/mutation.yml`.

### E27 - Drift found while writing the design docs (2026-10-08)

Found by checking every number and statement in the documents against
`eval/results/*.json`, the code and the git history while producing HLD.md, LLD.md and
this file.

- **Fixed in the documents.**
  - `architecture.md`: the funding-confidence trade-off quoted a 0.6 default and a 31%
    fallback rate (the code default is 0.5, `.env.example` sets 0.6, and the shipped run
    falls back on 40%, 14 of 35); the webhook section said "no signature verification"
    although it has been signed since E24; the provenance section said the three
    provisional fixtures included AFA (they are `mandate_revoked`, `mandate_expired` and
    `amount_exceeds_mandate`) and that four routes were all gated (two return 401).
  - `RESULTS.md`: Section 3 claimed the `unknown` payment cost the allocator "its one
    lucky recovery" (baseline recovers 0 of 1 there) and that baseline spends more
    attempts on `bank_technical` (9 against the allocator's 10); "two thirds" of the
    saved attempts was about 72%; "two of the seven fixtures" are provisional was three;
    the live-API paragraph conflated 401s with gating evidence.
  - `README.md`: a link to `eval/results/run_20260915T134833.json`, which does not
    exist (the frozen run is `run_20261008T100907`); a file-tree line listing
    `data/runs/` as tracked although it is git-ignored; a description of
    `logs/sample_run.jsonl` as showing "errors caught, fallback triggered" although it
    holds batch events from an earlier run and no error; the claim that four creation
    routes all returned a rejection; the Dependabot cadence (monthly, not weekly).
- **Found and not changed here** (outside documentation, or needing a re-run):
  - `eval/results/explanation_eval_{template,cached}.json` and their dashboard copies
    name `run_20260915T134833`, an earlier batch. Re-running them offline against the
    current run gives 88 of 88 and 7 of 7 passing every check; the committed files say
    91 of 91 and 4 of 7.
  - The 7 cached explanations in the frozen run are all `template_fallback`; no model
    output is stored in it.
  - `logs/sample_run.jsonl` is from `run_20260904T223013` and contains no caught error,
    so it does not yet satisfy the constraint of committing one sample that shows a real
    caught error. It shows the log format only.
  - Stale numbers in code comments: `eval/multiseed.py` and `eval/economics.py` still
    quote "29 vs 35", "7/27", "46% fewer" and a breakeven near Rs 157; the current
    values are 30 vs 35, 6/27, 50.4% fewer and Rs 147.82.
  - `render.yaml` declares `OPENROUTER_API_KEY`, but `pipeline/explain.py` reads
    `LLM_BASE_URL` and `LLM_API_KEY`; it also omits `CORS_ORIGINS` and
    `RAZORPAY_WEBHOOK_SECRET`. A deployment from the blueprint alone would use template
    wording and block the dashboard's browser calls until those are set (HLD.md Section 7).
  - The dashboard's document list (`dashboard/src/lib/site.js`) does not yet link
    `HLD.md`, `LLD.md` or this file.
  - The shipped batch never exercises the peak-window shift: failure times are off-peak
    and every default offset is a whole number of days (LLD.md Section 3.7).
- **Lesson.** Counts, names and cross-references should come from the artifacts, and the
  claims that guard the project's credibility are the ones to re-verify first.

## Patterns across the log

| Pattern | Entries |
|---|---|
| A result that looked wrong was a bug report | E03, E07, E12, E23 |
| A rule or comment existed but the code did not honour it | E08, E12, E19, E21 |
| Secrets handled through the shell or inlined | E01, E06, E13 |
| An environment limit reported honestly instead of worked around | E02, E14, E15 |
| A study assumption proved wrong and was reported, not hidden | E04, E22 |
| The dev-server and tooling gap that tests cannot see | E11, E17 |
| Prose copied from memory instead of the artifact | E14, E20, E27 |
