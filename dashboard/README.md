# Dashboard

A landing page first (`src/views/LandingPage.jsx`), then four tabs behind
one button. Story, Decision Trace, and Batch Results read only static
files in `public/data/` — no live API call, ever (PRD Sec 6.2's
demo-reliability requirement), because the batch study itself is meant to
be fixed and reproducible. Live Simulator is the one opt-in exception: it
calls a small local FastAPI backend that runs the real pipeline (never the
real Razorpay API).

## Run it

```
npm install
npm run dev
```

Story, Decision Trace, and Batch Results work immediately since their data
is committed to the repo. Live Simulator additionally needs the backend
running in a separate terminal from the repo root:

```
source ../.venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

## Refresh the data

Everything in `public/data/` is a copy of the Python eval scripts' own
output (batch run, sensitivity sweep, explanation eval, policy what-if). To update them after a new batch
run:

```
cd ..
python -m eval.harness
python -m eval.sensitivity
cp eval/results/run_*.json dashboard/public/data/latest_run.json
cp eval/results/sensitivity.json dashboard/public/data/sensitivity.json
python -m eval.explanation_eval --source template
python -m eval.explanation_eval --source cached
python -m eval.policy_whatif
cp eval/results/explanation_eval_*.json eval/results/policy_whatif.json dashboard/public/data/
```
