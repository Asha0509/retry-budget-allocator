# Recurring Payment Recovery — Retry Budget Allocator
Razorpay AI Buildathon 2026 — Track 3: AI Revenue Recovery

Full spec: /docs/prd.md — read the relevant section before implementing anything.
Cite the PRD section number in commit messages and comments. Use "Sec 4" style,
plain ASCII, never the section symbol.

Submission requirements (not deployment): public GitHub repo, 5-minute pitch
video, architecture documentation. There is NO live-deployment requirement.
Do not spend time on hosting, domains, Docker, or cloud deploy targets.

Evaluated on four separate axes: Problem Taste, Build Quality (clean repo,
execution reliability, code trust), AI Judgment (using models appropriately,
opting for deterministic solutions where AI is unnecessary), and Failure
Recovery (what broke during the build and how it was fixed). Failure Recovery
is graded on its own - see the Build log section below.

## What this system is

An agent that decides how to spend a scarce, regulated budget of recovery
attempts when a UPI AutoPay recurring payment fails. Three real intervention
branches: notify, retry at a chosen compliant time, or stop early.

## Hard constraints

- Compliance invariants are non-negotiable and must be unit-tested before any
  other logic is built (PRD Sec 7, build order step 2):
  - Never more than 3 retry attempts per mandate (NPCI cap: 1 original + 3).
  - Never schedule inside a peak window (10:00-13:00, 17:00-21:30).
  - Never more than one successful debit per token per billing cycle.
  These are the claims most likely to be challenged. Prove them in tests.
- Cause classification (Stage 2) is a DETERMINISTIC lookup over the Razorpay
  error object. Never an LLM call. This is the project's explicit answer to the
  AI Judgment criterion - do not "improve" it into a model call.
- The LLM is used in exactly one place (Stage 7): generating plain-language
  reasoning strings and customer-facing notification copy. It never decides
  whether to retry, when to retry, or whether to stop. Keep it off the critical
  path so an API outage degrades explanations, not decisions.
- All three intervention branches (notify / retry / stop) must be live and
  exercised in the batch. If everything collapses into "retry later", this
  becomes a scheduler, not an intervention-chooser, and the match to the track's
  "determines the right intervention" requirement breaks (PRD Sec 3).
- Funding-window inference (Stage 4) is PROBABILISTIC, never asserted as known.
  Below the confidence threshold, fall back to documented safe spacing
  (24h / 72h / 7d). The fallback is a designed feature, not a hidden weakness.
- Defense-only in spirit: the system never fabricates payment data, never
  bypasses NPCI limits, never games compliance windows.
- Every pipeline stage returns a structured trace entry (stage name, input
  summary, output summary, elapsed ms, skipped-with-reason if not run), not just
  its result. The dashboard renders these as the executing pipeline (PRD Sec
  6.1). Build this in from the first stage - retrofitting stage traces after the
  pipeline is written means rewriting every function signature.
- The allocator returns ALL scored candidate windows with rejection reasons, not
  only the winning choice. If it scores five windows internally and returns one,
  the reasoning is lost and the rejected-alternatives view cannot be built.
- The raw error payload is carried through the pipeline into the decision
  record, never discarded after classification.
- Demo reliability (PRD Sec 6.2): the dashboard reads saved run artifacts from
  data/runs/ by default, never live API calls. LLM explanation text is cached to
  disk with the run and never regenerated on load. A provider outage during the
  pitch recording must degrade nothing. Live mode is opt-in only.
- The README carries the problem statement, not just setup instructions. It is
  the first thing a judge opens on a public repo and Problem Taste is graded
  from what is visible there. Keep it current as results land.
- docs/RESULTS.md is a required artifact (PRD Sec 6.4), not optional polish.
  Raw JSON in eval/results/ is not a results write-up. State the outcome model
  BEFORE any number, include the sensitivity sweep, and include a "what did not
  work" section. Link it prominently from the README.
- A rendered documentation site is build order step 13 and is GATED on steps
  1-12 being complete (PRD Sec 6.5). GitHub already renders docs/ browsably with
  Mermaid support, so the marginal gain is presentation only. Do not start it
  before the eval harness produces real numbers - a polished site over an
  unfinished engine signals misplaced effort.
- The outcome model (PRD Sec 5.1) lives in its own module and the allocator
  NEVER imports it. Test-mode charge results are authored by us, so if the
  allocator can see the success model the evaluation is circular and worthless.
  Write and freeze the outcome model before tuning any allocator logic. Never
  adjust the outcome model to make results look better - if the allocator only
  wins under one parameter setting, that is the finding, report it (Sec 5.2).

## Claims that must never appear in code comments, docs, or pitch material

These were verified as false or overstated during research (PRD Sec 2). Do not
reintroduce them:
- Do NOT claim Razorpay's managed Subscriptions T+3 retry is "blind" or a flaw.
  That is a different product surface. The real, documented gap is that the
  controlled S2S UPI AutoPay flow does not auto-retry at all and hands retry to
  the merchant.
- Do NOT claim retry spacing is novel. 24/72/168h spacing is published best
  practice and Stripe ships ML-driven retries. The narrow novel claim is
  cause-classified allocation of a hard-capped budget with an explicit stop.
- Do NOT claim the system knows when a customer's salary arrives. It infers a
  likely funding window with a confidence score.
- Do NOT overstate dataset strength. The failure mix is modelled from published
  rates, not observed. Say so in the results write-up.
- Do NOT describe results as real-world recovery rates. Test-mode outcomes are
  authored by us. The honest claim is "the allocator spends a scarce budget well
  under a stated, published outcome model" - never "recovers X% of real
  payments". Phrase every headline number in the dashboard and pitch this way.
- Do NOT imply the whole batch ran live against the Razorpay API. Per PRD Sec
  5.0, a small integration tier runs end-to-end and the large batch replays that
  captured schema locally. State the split plainly in the write-up and video.

## Tool usage

- Backend: Python, Pydantic for decision records and schemas.
- LLM access: OpenRouter free-tier model (`:free` suffix - genuinely zero cost,
  no credit balance required), model name read from `.env` as
  `EXPLANATION_MODEL` so it can be swapped without code changes if a provider
  rate-limits mid-build. Do not switch to a paid or trial-credit endpoint;
  NVIDIA NIM gives trial credits that expire, not free usage.
- Secrets: every API key lives in a local `.env`, loaded via `python-dotenv`.
  `.env` is git-ignored. Never hardcode or commit keys.
- Errors: no silent failures. Wrap LLM calls and any API interaction in explicit
  try/except with logged, informative messages - there is no external error
  tracker during the demo recording.
- Tests: every pipeline stage needs a unit test before being marked done.
  `pytest --cov=pipeline --cov-report=term`.
- Dashboard (built last, PRD Sec 6): React + Tailwind + shadcn/ui. Three views -
  story, decision trace, batch results. Plain language leads, technical detail
  underneath. Do not start this before the eval harness produces real numbers.
- Diagrams: Mermaid inline in /docs markdown for architecture and pipeline flow.

## Presentation rule

Every user-facing string - dashboard labels, decision reasoning, notification
copy - must be understandable by someone who has never heard of NPCI, mandates,
or AutoPay. Plain sentence first, technical detail in secondary text. A
compliance officer should be able to read the audit trail without an engineer
translating it.

Plain language is the entry point, not the ceiling. The output must also let a
technical viewer verify the mechanism (PRD Sec 6.1): show rejected candidate
windows with their scores, show the expected-value arithmetic, show the raw
error payload beside its translation, run the compliance assertions live on
screen, and plot the sensitivity sweep. If a view only shows conclusions and
never shows the reasoning that produced them, it reads as a frontend with no
engine behind it - rebuild it.

## Continuous verification

- After each pipeline stage, run the Ponytail review step on the diff.
- Before starting a new PRD section, restate its acceptance criteria in 1-2
  sentences and confirm the previous section actually met them.
- Run a Ponytail audit pass before any commit that closes a build-order step.

## Source of truth

- /docs/prd.md is authoritative. Before implementing any section, restate its
  acceptance criteria and confirm the implementation satisfies every constraint
  listed there.
- If a PRD requirement conflicts with a Hard Constraint above, the Hard
  Constraint wins. Flag the conflict explicitly instead of quietly building the
  disallowed thing.
- Never silently drop a PRD requirement. If something cannot be built as
  specified in the current session, say so and log it as a gap.
- If a factual claim in the PRD cannot be traced to a source in Sec 2, flag it
  rather than building on it.

## Build log

Keep a running note in /docs/build-log.md of anything that actually breaks and
how it was fixed - a bug, a wrong assumption, a PRD gap caught mid-build. This
feeds the pitch video's Failure Recovery narrative, which is a separately graded
axis. Do not reconstruct it from memory at the end.

## Git identity and commit practices

- All commits must be authored under the human developer's own git identity,
  never a Claude/AI identity. Before the first commit in a session, verify
  `git config user.name` and `user.email` are set to the developer's own
  values, not a default or tool-generated one. If unset, stop and ask rather
  than committing with a placeholder identity.
- Commit messages are crisp, concise, and sound like a person wrote them under
  time pressure - not like generated documentation. No emoji, no
  "Co-Authored-By" trailers, no boilerplate closing paragraphs.
  - Good: `Add mandate cause classifier (Sec 4, Stage 2)`
  - Good: `Fix window scheduler allowing peak-hour retries`
  - Bad (too AI-generated-sounding): `Implement comprehensive mandate cause
    classification system with robust error handling and extensive test
    coverage for the payment recovery pipeline`
  - One line, imperative mood, states what changed and (if relevant) the PRD
    section. A body is fine for a real "why", but skip it if the subject line
    already says everything.
- One logical change per commit. Don't bundle an unrelated fix into a feature
  commit because it's convenient.

## Coding practices

- Type hints on every function signature - Pydantic models are already typed,
  keep the rest of the codebase consistent with that.
- Small functions with one clear responsibility. A pipeline stage function
  should be readable top to bottom without scrolling.
- Docstrings state what a function does and which PRD section it implements,
  not a restatement of the function name.
- No dead code, no commented-out blocks left in - delete it, git history keeps
  it if it's needed again.
- No print-based debugging left in committed code - use the logging setup
  described below.
- Ponytail active (full mode) - minimal code, reuse before rewrite, never cut
  validation, error handling, or security.

## `/logs/` - raw runtime evidence, separate from the build log

Every pipeline run writes structured, timestamped JSONL entries to `/logs/` as
it executes (stage entered/completed, errors caught, classification made,
fallback triggered) - this is what later gets mined to write
`docs/build-log.md` and the "what did not work" section of `docs/RESULTS.md`,
rather than relying on memory of what happened days earlier (PRD Sec 6.6).

- `/logs/` is git-ignored in bulk (large, regenerable) except one small
  committed sample showing a real caught error - raw evidence, not just a
  narrative claim about one.
- `docs/build-log.md` stays a short curated narrative for the pitch video, not
  a dump of every log line. Pull the real stories from `/logs/`, don't
  reconstruct them from memory.

## Repo layout

/pipeline /eval /dashboard /data /docs
(see PRD Sec 7 for what goes in each)
