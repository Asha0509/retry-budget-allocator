# Dashboard

Three views (Story / Decision Trace / Batch Results) over a saved batch run.
Reads only static files in `public/data/` - never a live API call (PRD Sec
6.2 demo-reliability requirement).

## Run it

```
npm install
npm run dev
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
