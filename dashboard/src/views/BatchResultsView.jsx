import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { runComplianceChecks } from '../lib/compliance.js'
import { causeLabel, formatMoney } from '../lib/format.js'

function StatCard({ label, baseline, allocator, format = (x) => x, better = 'higher' }) {
  const win = better === 'higher' ? allocator >= baseline : allocator <= baseline
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <div className="mt-2 flex items-baseline gap-3">
        <div>
          <p className="text-xs text-slate-400">baseline</p>
          <p className="text-lg font-semibold text-slate-500">{format(baseline)}</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">allocator</p>
          <p className={`text-lg font-semibold ${win ? 'text-emerald-600' : 'text-rose-600'}`}>{format(allocator)}</p>
        </div>
      </div>
    </div>
  )
}

function ComplianceLivePanel({ payments }) {
  const checks = useMemo(() => runComplianceChecks(payments), [payments])
  const rows = [checks.attemptCap, checks.peakWindow, checks.oneSuccessPerCycle]
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Compliance invariants - checked live against this batch, in your browser
      </h3>
      <div className="mt-3 space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
            <span className="text-slate-700">{r.label}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${r.passed ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'}`}>
              {r.passed ? 'PASS' : `FAIL (${r.violations.length})`}
              {r.checked !== undefined && ` · ${r.checked} checked`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function SensitivityChart({ sensitivity }) {
  const data = sensitivity.rows.map((r, i) => ({
    i,
    label: `d${r.funding_event_day}/s${r.funding_event_spread_days}/h${r.bank_technical_half_life_hours}`,
    recovered_advantage: r.recovered_advantage,
    holds: r.allocator_advantage_holds,
  }))
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Sensitivity sweep - allocator's recovery-count advantage over baseline across {sensitivity.rows.length} outcome-model settings
      </h3>
      <p className="mt-1 text-xs text-slate-500">
        Advantage holds at <strong>{sensitivity.advantage_holds_at_n_of_total}</strong> grid points. Not a universal win - reported
        honestly (PRD Sec 5.2), see the note below the chart.
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 16, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="i" tick={false} label={{ value: 'grid point', position: 'insideBottom', offset: -4, fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} label={{ value: 'payments recovered vs baseline', angle: -90, position: 'insideLeft', fontSize: 10 }} />
          <Tooltip formatter={(v) => v} labelFormatter={(_, p) => p?.[0]?.payload?.label ?? ''} />
          <Bar dataKey="recovered_advantage">
            {data.map((d, i) => (
              <Cell key={i} fill={d.holds ? '#059669' : '#e11d48'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-2 text-xs text-slate-500">
        Green = allocator recovers at least as many payments as baseline at that setting (never by more than 1). Red = it trails,
        worst when funding events are both early and tightly clustered. Attempts-spent efficiency (not shown here) holds at every one
        of the 27 settings - see docs/RESULTS.md Section 4 for the full breakdown of when and why raw recovery count is a near-tie.
      </p>
    </div>
  )
}

export default function BatchResultsView({ run, sensitivity }) {
  const { baseline, allocator } = run.results_table

  const attemptsSavedPct = Math.round((1 - allocator.attempts_spent / baseline.attempts_spent) * 100)
  const recoveredDelta = allocator.payments_recovered - baseline.payments_recovered

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-700">
        The finding: spending the same 3-attempt budget by cause instead of on a fixed schedule uses{' '}
        <strong>{attemptsSavedPct}% fewer retry attempts</strong> and wastes <strong>zero</strong> of them on payments that could never
        have succeeded (baseline wastes {baseline.attempts_wasted_on_unrecoverable_causes}) - the honest caveat is it does{' '}
        {recoveredDelta >= 0 ? 'also recover more payments' : `not recover more raw payments at these settings (${Math.abs(recoveredDelta)} fewer)`},
        and the sensitivity sweep below shows exactly when and why.
      </p>
      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
        Simulation study, not a live-payments measurement: test-mode outcomes are authored by a frozen, declared success model
        (eval/outcome_model.py), never seen by the allocator. This measures whether the allocator spends a scarce budget well under a
        stated model of the world - not real-world recovery.
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Attempts spent" baseline={baseline.attempts_spent} allocator={allocator.attempts_spent} better="lower" />
        <StatCard label="Payments recovered" baseline={baseline.payments_recovered} allocator={allocator.payments_recovered} />
        <StatCard label="₹ recovered" baseline={baseline.amount_recovered_paise} allocator={allocator.amount_recovered_paise} format={formatMoney} />
        <StatCard
          label="Attempts wasted on unrecoverable causes"
          baseline={baseline.attempts_wasted_on_unrecoverable_causes}
          allocator={allocator.attempts_wasted_on_unrecoverable_causes}
          better="lower"
        />
      </div>

      <ComplianceLivePanel payments={run.payments} />

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Per-cause breakdown (allocator)</h3>
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase tracking-wide text-slate-400">
              <th className="py-1 pr-2">Cause</th>
              <th className="py-1 pr-2">n</th>
              <th className="py-1 pr-2">Recovered</th>
              <th className="py-1 pr-2">Recovery rate</th>
              <th className="py-1">Attempts spent</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(run.per_cause_breakdown.allocator).map(([cause, row]) => (
              <tr key={cause} className="border-t border-slate-100">
                <td className="py-1.5 pr-2">{causeLabel(cause)}</td>
                <td className="py-1.5 pr-2">{row.n}</td>
                <td className="py-1.5 pr-2">{row.recovered}</td>
                <td className="py-1.5 pr-2">{(row.recovery_rate * 100).toFixed(0)}%</td>
                <td className="py-1.5">{row.attempts_spent}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Stop-decision precision</h3>
          <p className="mt-2 text-sm text-slate-600">
            Of payments the allocator stopped/notified instead of retrying,{' '}
            <strong>{((run.stop_decision_precision.allocator.precision ?? 0) * 100).toFixed(0)}%</strong> were genuinely unrecoverable
            under the frozen outcome model ({run.stop_decision_precision.allocator.n_stopped_early} stopped early).
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Confidence-fallback rate</h3>
          <p className="mt-2 text-sm text-slate-600">
            Of {run.confidence_fallback_rate.n_ran} `insufficient_funds` payments where funding-window inference (Stage 4) ran,{' '}
            <strong>{((run.confidence_fallback_rate.fallback_rate ?? 0) * 100).toFixed(0)}%</strong> had too little reliable history and
            fell back to documented safe spacing instead of a real estimate.
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Cause mix (modelled, not observed)</h3>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">
            {Object.entries(run.cause_mix).map(([cause, weight]) => (
              <li key={cause} className="flex justify-between">
                <span>{causeLabel(cause)}</span>
                <span className="font-mono text-xs">{(weight * 100).toFixed(0)}%</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <SensitivityChart sensitivity={sensitivity} />
    </div>
  )
}
