#!/usr/bin/env bash
# One-command validation: lint -> tests -> data contract -> eval gates -> dashboard build.
# Same checks CI runs. Usage: scripts/validate.sh [--skip-dashboard]
set -uo pipefail
cd "$(dirname "$0")/.."

STAGES=(); FAILED=0
stage() { # name, command...
  local name="$1"; shift
  local t0=$SECONDS
  echo; echo "==> $name"
  if "$@"; then STAGES+=("PASS  $name ($((SECONDS - t0))s)"); else STAGES+=("FAIL  $name ($((SECONDS - t0))s)"); FAILED=1; fi
}
finish() { echo; echo "---- validation summary ----"; printf "%s\n" "${STAGES[@]}"; exit $FAILED; }

stage "lint (ruff)" ruff check .
stage "unit tests + coverage" pytest --cov=pipeline --cov-report=term -q
stage "data contract (check only)" python -m eval.data_contract --check-only
stage "eval harness (compliance + outcome gates)" python -m eval.harness
stage "eval summary gate" python scripts/ci_eval_summary.py
if [[ "${1:-}" != "--skip-dashboard" && -d dashboard/node_modules ]]; then
  stage "dashboard lint + build" bash -c "cd dashboard && npm run lint && npm run build"
fi
finish
