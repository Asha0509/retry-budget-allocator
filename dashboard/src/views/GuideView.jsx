import { useMemo, useState } from 'react'
import { actionLabel, causeLabel, formatDateTime, formatMoney } from '../lib/format.js'
import { GLOSSARY } from '../lib/site.js'

// A guided walkthrough of one real failed payment from the saved batch run, so a
// first-time visitor can see what each stage does before opening the other tabs.

function pickExample(run) {
  return run.payments.find((p) => p.cause === 'insufficient_funds' && p.allocator_decisions[0].action === 'retry') ?? run.payments[0]
}

function Candidates({ decision }) {
  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead className="text-[11px] uppercase tracking-wide text-slate-400">
          <tr><th className="py-1 pr-3">Slot</th><th className="pr-3">When</th><th className="pr-3">Score</th><th>Result</th></tr>
        </thead>
        <tbody>
          {decision.candidates.map((c) => {
            const chosen = c.scheduled_at === decision.scheduled_at
            return (
              <tr key={c.offset_label + c.scheduled_at} className={chosen ? 'bg-indigo-50 font-medium' : ''}>
                <td className="py-1 pr-3 font-mono">{c.offset_label}</td>
                <td className="pr-3">{formatDateTime(c.scheduled_at)}</td>
                <td className="pr-3 font-mono tabular-nums">{c.score}</td>
                <td>{chosen ? 'Chosen' : c.rejected_reason ?? (c.compliant ? 'Lower score' : 'Not allowed')}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function buildSteps(p) {
  const d = p.allocator_decisions[0]
  const ex = p.explanation
  return [
    {
      title: 'The problem',
      plain: 'A customer set up an automatic payment. Today it failed. The rules allow only three more tries, and you cannot get a try back once it is used.',
      body: <p className="text-sm text-slate-600">So the real question is not “when do we retry?” but “is a retry the right move at all, and if so, when?”</p>,
      next: null,
    },
    {
      title: 'A payment fails',
      plain: `A ${formatMoney(p.amount)} payment failed on ${formatDateTime(p.failure_time)}. The bank sent back an error. We keep it untouched so it can be audited.`,
      body: <pre className="mt-3 overflow-x-auto rounded-md bg-slate-900 p-3 text-[12px] leading-relaxed text-slate-100">{JSON.stringify(p.raw_error, null, 2)}</pre>,
      next: { tab: 'trace', label: 'See the raw error beside its translation' },
    },
    {
      title: 'Why it failed',
      plain: `Reading the error: ${causeLabel(p.cause)}. This is a fixed lookup table, not a model, so the same error always gives the same answer.`,
      body: <p className="text-sm text-slate-600">Confidence: <span className="font-mono">{d.cause_confidence}</span>. Recoverable: <span className="font-mono">{String(d.recoverable)}</span>.</p>,
      next: null,
    },
    {
      title: 'When to try',
      plain: 'Every allowed time slot is scored, and we keep all the scores. Slots inside busy banking hours are never allowed.',
      body: <Candidates decision={d} />,
      next: { tab: 'trace', label: 'Open the full scored list and the arithmetic' },
    },
    {
      title: 'The decision',
      plain: `Decision: ${actionLabel(d.action)}${d.scheduled_at ? ` on ${formatDateTime(d.scheduled_at)}` : ''}. Attempts used so far: ${d.attempts_used} of 3.`,
      body: <p className="text-sm text-slate-600">Window allowed: <span className="font-mono">{String(d.window_compliant)}</span>. The three rules are checked again on every payment in the Batch Results tab.</p>,
      next: { tab: 'batch', label: 'Run the compliance checks live' },
    },
    {
      title: 'Saying it clearly',
      plain: ex ? 'A model wrote this reason and message after the decision was made. It cannot change the decision.' : 'Here a template wrote the message. A model can write it when one is available; the decision is the same either way.',
      body: (
        <div className="mt-3 space-y-2 text-sm text-slate-700">
          <p className="rounded-md bg-slate-50 p-3">{ex?.reasoning_plain ?? d.reasoning_plain}</p>
          {ex && <p className="rounded-md bg-slate-50 p-3">{ex.notification_copy_en}</p>}
          {ex && <p className="font-mono text-[11px] text-slate-400">written by: {ex.generated_by}</p>}
        </div>
      ),
      next: { tab: 'story', label: 'Read this payment as a story' },
    },
    {
      title: 'How it compares',
      plain: `A fixed schedule used ${p.baseline.attempts_spent} attempt(s) here; the allocator used ${p.allocator.attempts_spent}. Across the whole batch the allocator spends about half the attempts.`,
      body: <p className="text-sm text-slate-600">It does recover fewer payments overall, and the Policy What-If tab shows how that trade moves if you change the numbers.</p>,
      next: { tab: 'whatif', label: 'Change the assumptions yourself' },
    },
  ]
}

export default function GuideView({ run, goTo }) {
  const [i, setI] = useState(0)
  const payment = useMemo(() => (run ? pickExample(run) : null), [run])
  if (!payment) return <div className="py-12 text-center text-slate-500">Loading the example…</div>
  const steps = buildSteps(payment)
  const s = steps[i]

  return (
    <div className="grid gap-8 lg:grid-cols-3">
      <div className="lg:col-span-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-700">Follow one failed payment · step {i + 1} of {steps.length}</p>
        <div className="mt-2 flex gap-1">
          {steps.map((x, k) => (
            <button key={x.title} onClick={() => setI(k)} aria-label={x.title} className={`h-1.5 flex-1 rounded ${k <= i ? 'bg-indigo-600' : 'bg-slate-200'}`} />
          ))}
        </div>
        <div className="mt-5 rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="text-xl font-semibold text-slate-900">{s.title}</h2>
          <p className="mt-2 text-[15px] leading-relaxed text-slate-700">{s.plain}</p>
          {s.body}
          {s.next && (
            <button onClick={() => goTo(s.next.tab)} className="mt-4 text-sm font-medium text-indigo-700 underline underline-offset-2">{s.next.label}</button>
          )}
        </div>
        <div className="mt-4 flex justify-between">
          <button disabled={i === 0} onClick={() => setI(i - 1)} className="rounded-md border border-slate-300 px-4 py-2 text-sm disabled:opacity-40">Back</button>
          {i < steps.length - 1 ? (
            <button onClick={() => setI(i + 1)} className="rounded-md bg-slate-900 px-4 py-2 text-sm text-white hover:bg-indigo-700">Next</button>
          ) : (
            <button onClick={() => goTo('live')} className="rounded-md bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-700">Now try your own payment</button>
          )}
        </div>
      </div>

      <aside>
        <h3 className="text-sm font-semibold text-slate-900">What is what</h3>
        <dl className="mt-3 space-y-3">
          {GLOSSARY.map(([term, def]) => (
            <div key={term}>
              <dt className="text-[13px] font-medium text-slate-900">{term}</dt>
              <dd className="text-[12.5px] leading-snug text-slate-600">{def}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-6 rounded-md bg-slate-50 p-3 text-[12.5px] leading-snug text-slate-600">
          <p className="font-medium text-slate-900">The tabs</p>
          <p className="mt-1">Live Simulator computes a decision now. Story and Decision Trace explain one payment. Batch Results and Evals show all 60. Audit Trail lists every check. Policy What-If lets you change the assumptions.</p>
        </div>
      </aside>
    </div>
  )
}
