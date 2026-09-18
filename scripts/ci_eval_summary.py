"""Check the headline eval gates and print a Markdown summary for the CI run page.

Gates (any failure exits non-zero):
  * both policies schedule zero compliance violations,
  * the allocator wastes no attempts on causes that can never succeed,
  * the synthetic batch passes its data contract.

Reads the newest eval/results/run_*.json plus data_contract.json; run
`python -m eval.harness` and `python -m eval.data_contract` first.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "eval" / "results"


def latest_run() -> dict:
    runs = sorted(RESULTS.glob("run_*.json"))
    if not runs:
        raise SystemExit("no eval/results/run_*.json found; run `python -m eval.harness` first")
    return json.loads(runs[-1].read_text())


def gate_failures(run: dict, contract: dict) -> list[str]:
    table = run["results_table"]
    failures = []
    for policy, row in table.items():
        if row["compliance_violations"]:
            failures.append(f"{policy}: {row['compliance_violations']} compliance violations")
    if table["allocator"]["attempts_wasted_on_unrecoverable_causes"]:
        failures.append("allocator spent attempts on unrecoverable causes")
    if not contract["passed"]:
        failures.append(f"data contract failing rows: {contract['failing_rows_by_check']}")
    return failures


def _row(label: str, row: dict) -> str:
    cells = [
        label,
        row["attempts_spent"],
        row["payments_recovered"],
        row["attempts_wasted_on_unrecoverable_causes"],
        row["compliance_violations"],
    ]
    return "| " + " | ".join(str(c) for c in cells) + " |"


def render(run: dict, contract: dict, failures: list[str]) -> str:
    base, alloc = run["results_table"]["baseline"], run["results_table"]["allocator"]
    lines = [
        f"### Retry allocator eval `{run['run_id']}` ({run['n']} payments, seed {run['seed']})",
        "",
        "| Policy | Attempts | Recovered | Wasted attempts | Compliance violations |",
        "|---|---|---|---|---|",
        _row("Fixed schedule", base),
        _row("Allocator", alloc),
        "",
        f"Data contract ({contract['n']:,} events): **{'pass' if contract['passed'] else 'FAIL'}**",
        "",
        "Gates: " + ("all passed" if not failures else "FAILED - " + "; ".join(failures)),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    run = latest_run()
    contract = json.loads((RESULTS / "data_contract.json").read_text())
    failures = gate_failures(run, contract)
    text = render(run, contract, failures)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(text)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
