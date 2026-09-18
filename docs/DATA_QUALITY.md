# Synthetic data quality (Retry Budget Allocator)

No real failed-payment data exists for this project, so realism cannot be measured against ground truth.
What is checked instead is **rule compliance**: every generated row must obey the published rules of the
payment rails it imitates. The contract is a Pandera schema in `eval/data_contract.py`.

Batch: 5,000 events, seed 42. Result: **PASS**.

| Rule | Source | Failing rows |
|---|---|---|
| `npci_first_attempt_offpeak` | NPCI peak windows 10:00-13:00, 17:00-21:30 IST | 0 |
| `rbi_afa_threshold` | RBI: debits above Rs 15,000 need additional authentication | 0 |
| `razorpay_mandate_cap` | Razorpay mandate: debit may not exceed the registered cap | 0 |
| `documented_error_reason` | Razorpay payment error documentation | 0 |
| `one_debit_per_cycle_history` | At most one successful debit per billing cycle | 0 |

## What this does not show

Passing means the data is *possible* under the rules, not that real traffic looks like it. The cause mix,
amount distribution and funding-day behaviour are modelled assumptions (see `docs/RESULTS.md`).

Profile: median amount Rs 1,499, 33% of events carry usable debit history.
