import { Fragment, useMemo, useState } from 'react'
import { isPeakWindow } from '../lib/compliance.js'
import { downloadCsv, toCsv } from '../lib/csv.js'
import { actionLabel, causeLabel, formatDateTime, formatMoney } from '../lib/format.js'

// One row per allocator decision in the saved run, with the three PRD Sec 2
// invariants re-checked per row in the browser - the view a compliance
// officer reads without an engineer translating (PRD Sec 6 presentation rule).

const MAX_ATTEMPTS = 3

function checksFor(d) {
  return [
    { label: 'Within 3 retries', passed: d.attempts_used <= MAX_ATTEMPTS },
    { label: 'Outside busy hours', passed: !d.scheduled_at || !isPeakWindow(d.scheduled_at), na: !d.scheduled_at },
    { label: 'No retry after a successful payment', passed: !(d.action === 'retry' && d.billing_cycle_successes >= 1) },
  ]
}

function flatten(payments) {
  return payments.flatMap((p) =>
    (p.allocator_decisions ?? []).map((d, i) => ({
      key: `${p.payment_id}-${i}`,
      payment: p,
      decision: d,
      step: i + 1,
      checks: checksFor(d),
      rejected: d.candidates.filter((c) => !c.compliant).length,
    })),
  )
}

const OUTCOMES = {
  recovered: (r) => r.payment.allocator.recovered,
  not_recovered: (r) => !r.payment.allocator.recovered,
}

const CSV_COLUMNS = [
  { label: 'payment_id', value: (r) => r.payment.payment_id },
  { label: 'decision_step', value: (r) => r.step },
  { label: 'amount_inr', value: (r) => (r.decision.amount / 100).toFixed(2) },
  { label: 'cause', value: (r) => r.decision.cause },
  { label: 'cause_plain', value: (r) => causeLabel(r.decision.cause) },
  { label: 'classifier_confidence', value: (r) => r.decision.cause_confidence },
  { label: 'action', value: (r) => r.decision.action },
  { label: 'scheduled_at', value: (r) => r.decision.scheduled_at ?? '' },
  { label: 'attempts_used', value: (r) => r.decision.attempts_used },
  { label: 'attempts_remaining', value: (r) => r.decision.attempts_remaining },
  { label: 'windows_considered', value: (r) => r.decision.candidates.length },
  { label: 'windows_rejected_peak', value: (r) => r.rejected },
  { label: 'check_within_cap', value: (r) => r.checks[0].passed },
  { label: 'check_outside_peak', value: (r) => (r.checks[1].na ? 'n/a' : r.checks[1].passed) },
  { label: 'check_no_retry_after_success', value: (r) => r.checks[2].passed },
  { label: 'error_code', value: (r) => r.decision.raw_error.code ?? '' },
  { label: 'error_reason', value: (r) => r.decision.raw_error.reason ?? '' },
  { label: 'reasoning_plain', value: (r) => r.decision.reasoning_plain },
  { label: 'reasoning_technical', value: (r) => r.decision.reasoning_technical },
  { label: 'payment_recovered', value: (r) => r.payment.allocator.recovered },
]

function Checks({ checks }) {
  const failed = checks.filter((c) => !c.passed)
  if (failed.length === 0) {
    return <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">All 3 pass</span>
  }
  return (
    <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">
      Failed: {failed.map((c) => c.label).join(', ')}
    </span>
  )
}

function Detail({ r }) {
  const d = r.decision
  return (
    <div className="grid gap-4 bg-slate-50 p-4 text-xs md:grid-cols-2">
      <div className="space-y-2">
        <p className="text-sm text-slate-800">{d.reasoning_plain}</p>
        <p className="font-mono text-slate-500">{d.reasoning_technical}</p>
        <ul className="space-y-1">
          {r.checks.map((c) => (
            <li key={c.label} className={c.passed ? 'text-emerald-700' : 'text-rose-700'}>
              {c.passed ? '✓' : '✗'} {c.label}{c.na ? ' (nothing scheduled)' : ''}
            </li>
          ))}
        </ul>
        {d.candidates.length > 0 && (
          <table className="w-full text-left">
            <thead className="text-slate-400">
              <tr><th className="py-1 font-medium">Window</th><th className="font-medium">Time</th><th className="text-right font-medium">Score</th><th className="pl-2 font-medium">Status</th></tr>
            </thead>
            <tbody>
              {d.candidates.map((c) => (
                <tr key={c.offset_label} className={c.scheduled_at === d.scheduled_at ? 'font-semibold text-slate-900' : 'text-slate-600'}>
                  <td className="py-0.5 font-mono">{c.offset_label}</td>
                  <td>{formatDateTime(c.scheduled_at)}</td>
                  <td className="text-right font-mono">{c.score}</td>
                  <td className="pl-2">{c.compliant ? (c.scheduled_at === d.scheduled_at ? 'chosen' : 'allowed') : 'rejected: busy hours'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div>
        <p className="mb-1 font-semibold uppercase tracking-wide text-slate-400">Raw error from the payment provider</p>
        <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded bg-white p-2 font-mono text-slate-700">
          {JSON.stringify(d.raw_error, null, 2)}
        </pre>
      </div>
    </div>
  )
}

export default function AuditTrailView({ run }) {
  const all = useMemo(() => flatten(run.payments), [run])
  const [cause, setCause] = useState('')
  const [action, setAction] = useState('')
  const [outcome, setOutcome] = useState('')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(null)

  const causes = useMemo(() => [...new Set(all.map((r) => r.decision.cause))].sort(), [all])
  const rows = all.filter(
    (r) =>
      (!cause || r.decision.cause === cause) &&
      (!action || r.decision.action === action) &&
      (!outcome || OUTCOMES[outcome](r)) &&
      (!query || r.payment.payment_id.toLowerCase().includes(query.trim().toLowerCase())),
  )
  const failing = all.filter((r) => r.checks.some((c) => !c.passed)).length
  const select = 'mt-1 block w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm'

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Every decision, with the checks behind it</h2>
        <p className="mt-1 text-sm text-slate-600">
          {all.length} decisions across {run.payments.length} failed payments in run <span className="font-mono">{run.run_id}</span>.
          Each row re-checks the three payment-network rules in your browser:{' '}
          <strong className={failing ? 'text-rose-700' : 'text-emerald-700'}>
            {failing ? `${failing} rows break a rule` : 'every row passes all three'}
          </strong>
          . Open a row for the reasoning, every time slot that was considered, and the raw error it was based on.
        </p>
      </div>

      <div className="grid gap-3 rounded-lg border border-slate-200 bg-white p-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-xs font-medium text-slate-500">Why it failed
          <select className={select} value={cause} onChange={(e) => setCause(e.target.value)}>
            <option value="">All reasons</option>
            {causes.map((c) => <option key={c} value={c}>{causeLabel(c)}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-500">Decision
          <select className={select} value={action} onChange={(e) => setAction(e.target.value)}>
            <option value="">All decisions</option>
            {['retry', 'notify', 'stop'].map((a) => <option key={a} value={a}>{actionLabel(a)}</option>)}
          </select>
        </label>
        <label className="text-xs font-medium text-slate-500">Outcome for the payment
          <select className={select} value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="">All</option>
            <option value="recovered">Payment recovered</option>
            <option value="not_recovered">Not recovered</option>
          </select>
        </label>
        <label className="text-xs font-medium text-slate-500">Payment id
          <input className={select} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="pay_SYNTH000…" />
        </label>
        <div className="flex items-end">
          <button
            className="w-full rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            disabled={rows.length === 0}
            onClick={() => downloadCsv(`audit_trail_${run.run_id}.csv`, toCsv(CSV_COLUMNS, rows))}
          >
            Download {rows.length} rows as CSV
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-3 py-2 font-medium">Payment</th>
              <th className="px-3 py-2 font-medium">Why it failed</th>
              <th className="px-3 py-2 font-medium">Decision</th>
              <th className="px-3 py-2 font-medium">When</th>
              <th className="px-3 py-2 font-medium">Rules</th>
              <th className="px-3 py-2 font-medium">Payment outcome</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-500">No decisions match these filters.</td></tr>
            )}
            {rows.map((r) => (
              <Fragment key={r.key}>
                <tr className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" onClick={() => setOpen(open === r.key ? null : r.key)}>
                  <td className="px-3 py-2">
                    <button className="text-left font-mono text-xs text-indigo-700 underline-offset-2 hover:underline" aria-expanded={open === r.key}>
                      {r.payment.payment_id}
                    </button>
                    <div className="text-xs text-slate-400">{formatMoney(r.decision.amount)} · step {r.step}</div>
                  </td>
                  <td className="px-3 py-2 text-slate-700">{causeLabel(r.decision.cause)}</td>
                  <td className="px-3 py-2">
                    <span className="font-medium text-slate-800">{actionLabel(r.decision.action)}</span>
                    {r.decision.action === 'retry' && (
                      <div className="text-xs text-slate-400">retry {r.decision.attempts_used + 1} of {MAX_ATTEMPTS}</div>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-600">
                    {r.decision.scheduled_at ? formatDateTime(r.decision.scheduled_at) : '—'}
                    {r.rejected > 0 && <div className="text-slate-400">{r.rejected} busy-hour slot{r.rejected > 1 ? 's' : ''} rejected</div>}
                  </td>
                  <td className="px-3 py-2"><Checks checks={r.checks} /></td>
                  <td className="px-3 py-2 text-xs">
                    {r.payment.allocator.recovered
                      ? <span className="text-emerald-700">Recovered {formatMoney(r.payment.allocator.amount_recovered)}</span>
                      : <span className="text-slate-500">Not recovered</span>}
                  </td>
                </tr>
                {open === r.key && (
                  <tr className="border-b border-slate-200"><td colSpan={6} className="p-0"><Detail r={r} /></td></tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
