# Dashboard

Four tabs. Story / Decision Trace / Batch Results read only static files in
`public/data/` - never a live API call (PRD Sec 6.2 demo-reliability
requirement); the batch study itself is fixed and pre-computed. Live
Simulator is the one opt-in exception - it calls a small local FastAPI
backend that runs the real pipeline (never the real Razorpay API).

## Run it

```
npm install
npm run dev
```

Story, Decision Trace, and Batch Results work immediately - their data is
committed to the repo. Live Simulator additionally needs the backend running
in a separate terminal from the repo root:

```
source ../.venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

## Refresh the data

`public/data/latest_run.json` and `public/data/sensitivity.json` are copies
of the real output from the Python eval harness. To update them after a new
batch run:

```
cd ..
python -m eval.harness
python -m eval.sensitivity
cp eval/results/run_*.json dashboard/public/data/latest_run.json
cp eval/results/sensitivity.json dashboard/public/data/sensitivity.json
```
