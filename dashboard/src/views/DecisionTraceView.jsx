import { actionLabel, causeLabel, formatDateTime, formatMoney } from '../lib/format.js'

const STAGE_LABELS = {
  classify: 'Classify (Stage 2) - what did the bank say?',
  priors: 'Priors (Stage 3) - is this fixable?',
  funding_window: 'Funding window (Stage 4) - when might the account be funded?',
  allocate: 'Allocate (Stage 5) - spend an attempt, wait, or stop?',
  decision: 'Decision (Stage 6) - record the outcome',
  explain: 'Explain (Stage 7) - plain-language write-up',
}

function StageRow({ trace }) {
  return (
    <div className={`rounded-md border p-3 text-sm ${trace.skipped ? 'border-slate-200 bg-slate-50 text-slate-400' : 'border-slate-200 bg-white'}`}>
      <div className="flex items-center justify-between">
        <span className="font-medium text-slate-700">{STAGE_LABELS[trace.stage] ?? trace.stage}</span>
        <span className="text-xs text-slate-400">{trace.skipped ? 'skipped' : `${trace.elapsed_ms.toFixed(2)} ms`}</span>
      </div>
      {trace.skipped ? (
        <p className="mt-1 text-xs">Skipped: {trace.skip_reason}</p>
      ) : (
        <div className="mt-1 grid grid-cols-2 gap-2 text-xs text-slate-500">
          <p>in: {trace.input_summary}</p>
          <p>out: {trace.output_summary}</p>
        </div>
      )}
    </div>
  )
}

function CandidateTable({ candidates }) {
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="text-xs uppercase tracking-wide text-slate-400">
          <th className="py-1 pr-2">Offset</th>
          <th className="py-1 pr-2">When</th>
          <th className="py-1 pr-2">Score</th>
          <th className="py-1">Status</th>
        </tr>
      </thead>
      <tbody>
        {candidates.map((c, i) => (
          <tr key={i} className={`border-t border-slate-100 ${c.compliant ? '' : 'text-rose-500'}`}>
            <td className="py-1.5 pr-2 font-mono text-xs">{c.offset_label}</td>
            <td className="py-1.5 pr-2">{formatDateTime(c.scheduled_at)}</td>
            <td className="py-1.5 pr-2 font-mono text-xs">{c.score}</td>
            <td className="py-1.5 text-xs">
              {c.compliant ? (
                <span className="text-emerald-600">considered</span>
              ) : (
                <span>rejected: {c.rejected_reason}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function DecisionTraceView({ payment }) {
  if (!payment) return null
  const decisions = payment.allocator_decisions ?? []
  const traceSets = payment.allocator_stage_traces ?? []

  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Raw Razorpay error object</h3>
          <pre className="mt-2 overflow-x-auto rounded bg-slate-900 p-3 text-xs text-emerald-300">
            {JSON.stringify(payment.raw_error, null, 2)}
          </pre>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Plain-language translation</h3>
          <p className="mt-2 text-sm text-slate-700">
            <strong>{causeLabel(payment.cause)}</strong> (classifier confidence {decisions[0]?.cause_confidence ?? '—'})
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Matched deterministically from the error's <code>reason</code>/<code>description</code> fields - no model call (PRD Sec 4,
            Stage 2 hard constraint).
          </p>
        </div>
      </div>

      {decisions.map((decision, attemptIndex) => (
        <div key={attemptIndex} className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700">
              Attempt {attemptIndex + 1} - {actionLabel(decision.action)}
            </h3>
            <span className="text-xs text-slate-400">
              {decision.attempts_used} used / {decision.attempts_remaining} remaining of 3
            </span>
          </div>

          <div className="mb-3 space-y-2">
            {(traceSets[attemptIndex] ?? []).map((t, i) => (
              <StageRow key={i} trace={t} />
            ))}
          </div>

          {decision.candidates?.length > 0 && (
            <div className="mt-3">
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Every candidate window scored (not just the winner)
              </h4>
              <CandidateTable candidates={decision.candidates} />
              <p className="mt-1 text-xs text-slate-400">
                Score = recoverability × a declared offset preference (not a probability - the real outcome model is deliberately
                isolated from this scoring, PRD Sec 5.1).
              </p>
            </div>
          )}

          <p className="mt-3 rounded-md bg-slate-50 p-2 text-xs text-slate-500">{decision.reasoning_technical}</p>
        </div>
      ))}

      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
        Final: {payment.allocator.recovered ? `Recovered ${formatMoney(payment.allocator.amount_recovered)}` : 'Not recovered'} using{' '}
        {payment.allocator.attempts_spent} of 3 attempts. Compliance violations this payment:{' '}
        <strong>{payment.allocator.compliance_violations.length}</strong>.
      </div>
    </div>
  )
}
