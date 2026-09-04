import { useMemo, useState } from 'react'
import BatchResultsView from './views/BatchResultsView.jsx'
import DecisionTraceView from './views/DecisionTraceView.jsx'
import StoryView from './views/StoryView.jsx'
import { useRunData } from './lib/useRunData.js'

const TABS = [
  { id: 'story', label: 'Story' },
  { id: 'trace', label: 'Decision Trace' },
  { id: 'batch', label: 'Batch Results' },
]

export default function App() {
  const { loading, error, run, sensitivity } = useRunData()
  const [tab, setTab] = useState('story')
  const [selectedPaymentId, setSelectedPaymentId] = useState(null)

  const selectedPayment = useMemo(() => {
    if (!run) return null
    if (selectedPaymentId) return run.payments.find((p) => p.payment_id === selectedPaymentId)
    return run.payments.find((p) => p.explanation?.generated_by === 'llm') ?? run.payments[0]
  }, [run, selectedPaymentId])

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-slate-500">Loading run…</div>
  }
  if (error) {
    return (
      <div className="flex h-screen items-center justify-center p-8 text-center text-rose-600">
        Could not load a saved run artifact ({error.message}). Run <code className="rounded bg-rose-50 px-1">python -m eval.harness</code>{' '}
        and copy the output into <code className="rounded bg-rose-50 px-1">dashboard/public/data/</code>.
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <header className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-700">Razorpay AI Buildathon - Track 3: AI Revenue Recovery</p>
        <h1 className="mt-1 text-2xl font-semibold text-slate-900">Retry Budget Allocator</h1>
        <p className="mt-1 text-sm text-slate-600">
          When a UPI AutoPay payment fails, Razorpay hands the merchant exactly 3 retry attempts and no auto-retry - most businesses
          spend that budget on a fixed schedule that ignores why the payment failed. This decides how to spend it deliberately instead.
        </p>
        <p className="mt-2 text-xs text-slate-400">
          Simulation study over {run.n} synthesized failed payments (seed {run.seed}).
        </p>
      </header>

      <nav className="mb-6 flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition ${
              tab === t.id ? 'border-b-2 border-blue-600 text-blue-700' : 'text-slate-500 hover:text-slate-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {(tab === 'story' || tab === 'trace') && (
        <div className="mb-4">
          <label className="text-xs font-medium uppercase tracking-wide text-slate-400">Payment</label>
          <select
            className="mt-1 block w-full max-w-md rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
            value={selectedPayment?.payment_id ?? ''}
            onChange={(e) => setSelectedPaymentId(e.target.value)}
          >
            {run.payments.map((p) => (
              <option key={p.payment_id} value={p.payment_id}>
                {p.payment_id} — {p.cause} {p.explanation ? '(has LLM explanation)' : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      {tab === 'story' && <StoryView payment={selectedPayment} />}
      {tab === 'trace' && <DecisionTraceView payment={selectedPayment} />}
      {tab === 'batch' && <BatchResultsView run={run} sensitivity={sensitivity} />}
    </div>
  )
}
