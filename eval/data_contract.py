"""Data contract for the synthetic failed-payment batch (Pandera).

There is no real failed-payment data behind this project, so "is the data
realistic?" cannot be answered by comparing against ground truth. What can be
checked is whether every row obeys the published rules of the payment rails
the events come from. This module encodes those rules as a Pandera schema and
runs it over a generated batch:

* NPCI: first attempts are made outside the peak windows (10:00-13:00 and
  17:00-21:30 IST).
* RBI: debits above Rs 15,000 need additional factor authentication, so
  `afa_required` failures sit above that threshold and ordinary ones do not.
* Razorpay mandates: a debit may not exceed the registered mandate cap, and
  `amount_exceeds_mandate` failures are exactly the ones that do.
* Razorpay error documentation: each cause carries a documented error reason.
* At most one successful debit per billing cycle, so prior debit history has
  one entry per calendar month.

Usage:
    python -m eval.data_contract            # generate, validate, write reports
    python -m eval.data_contract --check-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

from eval.batch_generator import generate_batch
from pipeline.compliance import is_peak_window
from pipeline.ingest import FailedPaymentEvent
from pipeline.models import FailureCause

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = ROOT / "eval" / "results" / "data_contract.json"
REPORT_PATH = ROOT / "docs" / "DATA_QUALITY.md"

AFA_THRESHOLD_PAISE = 15_000 * 100

# The Razorpay `reason` string each fixture carries (documented error list).
DOCUMENTED_REASONS: dict[str, set[str]] = {
    FailureCause.INSUFFICIENT_FUNDS.value: {"insufficient_funds"},
    FailureCause.AFA_REQUIRED.value: {"authentication_failed"},
}


def _check_first_attempt_offpeak(df: pd.DataFrame) -> pd.Series:
    return ~df["failure_time"].apply(is_peak_window)


def _check_afa_threshold(df: pd.DataFrame) -> pd.Series:
    is_afa = df["cause"] == FailureCause.AFA_REQUIRED.value
    return (is_afa & (df["amount"] > AFA_THRESHOLD_PAISE)) | (~is_afa & (df["amount"] <= AFA_THRESHOLD_PAISE))


def _check_mandate_cap(df: pd.DataFrame) -> pd.Series:
    exceeds = df["amount"] > df["mandate_max_amount"]
    is_exceed_cause = df["cause"] == FailureCause.AMOUNT_EXCEEDS_MANDATE.value
    afa_exempt = df["cause"] == FailureCause.AFA_REQUIRED.value
    return (is_exceed_cause & exceeds) | (~is_exceed_cause & (~exceeds | afa_exempt))


def _check_documented_reason(df: pd.DataFrame) -> pd.Series:
    def ok(row: pd.Series) -> bool:
        allowed = DOCUMENTED_REASONS.get(row["cause"])
        return allowed is None or row["reason"] in allowed

    return df.apply(ok, axis=1)


def _check_one_debit_per_cycle(df: pd.DataFrame) -> pd.Series:
    def ok(dates: list) -> bool:
        months = [(d.year, d.month) for d in dates]
        return len(months) == len(set(months))

    return df["prior_debit_dates"].apply(ok)


SCHEMA = pa.DataFrameSchema(
    columns={
        "payment_id": pa.Column(str, unique=True),
        "cause": pa.Column(str, pa.Check.isin([c.value for c in FailureCause])),
        "amount": pa.Column(int, pa.Check.gt(0)),
        "mandate_max_amount": pa.Column(int, pa.Check.gt(0)),
        "attempts_used": pa.Column(int, pa.Check.in_range(0, 3)),
        "failure_time": pa.Column(checks=pa.Check(lambda s: s.notna().all() and getattr(s.dt, "tz", None) is not None, name="timezone_aware", element_wise=False)),
        "reason": pa.Column(str, nullable=True),
        "prior_debit_dates": pa.Column(object),
    },
    checks=[
        pa.Check(_check_first_attempt_offpeak, name="npci_first_attempt_offpeak"),
        pa.Check(_check_afa_threshold, name="rbi_afa_threshold"),
        pa.Check(_check_mandate_cap, name="razorpay_mandate_cap"),
        pa.Check(_check_documented_reason, name="documented_error_reason"),
        pa.Check(_check_one_debit_per_cycle, name="one_debit_per_cycle_history"),
    ],
    strict=True,
)


def to_frame(events: list[FailedPaymentEvent]) -> pd.DataFrame:
    """Flatten ingested events into one row each, tagged with the cause the fixture encodes."""
    from pipeline.classify import classify_cause

    rows = [
        {
            "payment_id": e.payment_id,
            "cause": classify_cause(e.error).cause.value,
            "amount": e.amount,
            "mandate_max_amount": e.mandate_max_amount,
            "attempts_used": e.attempts_used,
            "failure_time": e.failure_time,
            "reason": e.error.reason,
            "prior_debit_dates": list(e.prior_debit_dates),
        }
        for e in events
    ]
    return pd.DataFrame(rows)


def check(df: pd.DataFrame) -> dict[str, int]:
    """Validate the frame lazily; return the number of failing rows per named check."""
    failures: dict[str, int] = {c.name: 0 for c in SCHEMA.checks}
    try:
        SCHEMA.validate(df, lazy=True)
    except pa.errors.SchemaErrors as err:
        for _, row in err.failure_cases.iterrows():
            name = str(row.get("check"))
            failures[name] = failures.get(name, 0) + 1
    return failures


def profile(df: pd.DataFrame) -> dict:
    """Plain descriptive numbers for the report (counts, amount spread, history depth)."""
    return {
        "rows": int(len(df)),
        "cause_share": {k: round(v, 3) for k, v in df["cause"].value_counts(normalize=True).items()},
        "amount_rupees": {
            "min": float(df["amount"].min() / 100),
            "median": float(df["amount"].median() / 100),
            "max": float(df["amount"].max() / 100),
        },
        "with_history_share": round(float((df["prior_debit_dates"].apply(len) > 0).mean()), 3),
    }


def run(n: int = 5000, seed: int = 42) -> dict:
    df = to_frame(generate_batch(n, seed=seed))
    failures = check(df)
    return {"n": n, "seed": seed, "failing_rows_by_check": failures, "passed": not any(failures.values()), "profile": profile(df)}


def render_markdown(result: dict) -> str:
    lines = [
        "# Synthetic data quality (Retry Budget Allocator)",
        "",
        "No real failed-payment data exists for this project, so realism cannot be measured against ground truth.",
        "What is checked instead is **rule compliance**: every generated row must obey the published rules of the",
        "payment rails it imitates. The contract is a Pandera schema in `eval/data_contract.py`.",
        "",
        f"Batch: {result['n']:,} events, seed {result['seed']}. Result: **{'PASS' if result['passed'] else 'FAIL'}**.",
        "",
        "| Rule | Source | Failing rows |",
        "|---|---|---|",
    ]
    sources = {
        "npci_first_attempt_offpeak": "NPCI peak windows 10:00-13:00, 17:00-21:30 IST",
        "rbi_afa_threshold": "RBI: debits above Rs 15,000 need additional authentication",
        "razorpay_mandate_cap": "Razorpay mandate: debit may not exceed the registered cap",
        "documented_error_reason": "Razorpay payment error documentation",
        "one_debit_per_cycle_history": "At most one successful debit per billing cycle",
    }
    for name, count in result["failing_rows_by_check"].items():
        lines.append(f"| `{name}` | {sources.get(name, '')} | {count} |")
    prof = result["profile"]
    lines += [
        "",
        "## What this does not show",
        "",
        "Passing means the data is *possible* under the rules, not that real traffic looks like it. The cause mix,",
        "amount distribution and funding-day behaviour are modelled assumptions (see `docs/RESULTS.md`).",
        "",
        f"Profile: median amount Rs {prof['amount_rupees']['median']:,.0f}, "
        f"{prof['with_history_share']:.0%} of events carry usable debit history.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--check-only", action="store_true", help="validate and exit non-zero on failure; write nothing")
    args = parser.parse_args()
    result = run(args.n, args.seed)
    if not args.check_only:
        RESULTS_PATH.write_text(json.dumps(result, indent=2) + "\n")
        REPORT_PATH.write_text(render_markdown(result))
    print(json.dumps(result["failing_rows_by_check"], indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
