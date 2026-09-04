import { useEffect, useState } from 'react'
import { FAILURE_CAUSES, fetchPersonas, runSimulation, toPaymentShape } from '../lib/simulate.js'
import { causeLabel } from '../lib/format.js'
import StoryView from './StoryView.jsx'
import DecisionTraceView from './DecisionTraceView.jsx'

const STAGE_LABELS = {
  ingest: 'Ingest',
  classify: 'Classify',
  priors: 'Priors',
  funding_window: 'Funding window',
  allocate: 'Allocate',
  decision: 'Decision',
  explain: 'Explain',
}

function PersonaCard({ persona, selected, onSelect }) {
  return (
    <button
      onClick={() => onSelect(persona.key)}
      className={`rounded-lg border p-4 text-left transition ${
        selected ? 'border-blue-500 bg-blue-50' : 'border-slate-200 bg-white hover:border-slate-300'
      }`}
    >
      <p className="font-semibold text-slate-800">{persona.name}</p>
      <p className="mt-1 text-xs text-slate-500">{persona.description}</p>
    </button>
  )
}

function StatusStrip({ traces, revealedCount }) {
  return (
    <div className="flex flex-wrap gap-2">
      {traces.map((t, i) => {
        const revealed = i < revealedCount
        return (
          <div
            key={i}
            className={`rounded-full border px-3 py-1 text-xs transition-opacity duration-300 ${
              revealed ? 'opacity-100' : 'opacity-0'
            } ${t.skipped ? 'border-slate-200 bg-slate-50 text-slate-400' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}
          >
            {STAGE_LABELS[t.stage] ?? t.stage}
            {!t.skipped && <span className="ml-1.5 font-mono text-[10px] text-slate-400">{t.elapsed_ms.toFixed(1)}ms</span>}
          </div>
        )
      })}
    </div>
  )
}

export default function LiveSimulatorView() {
  const [personas, setPersonas] = useState([])
  const [backendError, setBackendError] = useState(null)
  const [mode, setMode] = useState('persona')
  const [selectedPersonaKey, setSelectedPersonaKey] = useState(null)

  const [amount, setAmount] = useState(50000)
  const [cause, setCause] = useState('insufficient_funds')
  const [useRawError, setUseRawError] = useState(false)
  const [rawErrorText, setRawErrorText] = useState('{\n  "code": "BAD_REQUEST_ERROR",\n  "reason": "insufficient_funds",\n  "description": "Customer bank account did not have enough funds"\n}')
  const [priorDebitDay, setPriorDebitDay] = useState('')
  const [nPriorDebits, setNPriorDebits] = useState(0)

  const [loading, setLoading] = useState(false)
  const [runError, setRunError] = useState(null)
  const [result, setResult] = useState(null)
  const [revealedCount, setRevealedCount] = useState(0)
  const [resultTab, setResultTab] = useState('story')

  useEffect(() => {
    fetchPersonas()
      .then(setPersonas)
      .catch((e) => setBackendError(e.message))
  }, [])

  useEffect(() => {
    if (!result) return
    const traces = result.allocator_stage_traces
    let i = 0
    const interval = setInterval(() => {
      i += 1
      setRevealedCount(i)
      if (i >= traces.length) clearInterval(interval)
    }, 220)
    return () => clearInterval(interval)
  }, [result])

  async function handleRun() {
    setLoading(true)
    setRunError(null)
    setResult(null)
    try {
      let body
      if (mode === 'persona') {
        if (!selectedPersonaKey) throw new Error('Pick a persona first')
        body = { persona: selectedPersonaKey }
      } else if (useRawError) {
        let raw_error
        try {
          raw_error = JSON.parse(rawErrorText)
        } catch {
          throw new Error('Raw error JSON is not valid JSON')
        }
        body = { raw_error, amount: Number(amount) }
      } else {
        body = {
          cause,
          amount: Number(amount),
          prior_debit_day_of_month: priorDebitDay ? Number(priorDebitDay) : null,
          n_prior_debits: Number(nPriorDebits) || 0,
        }
      }
      const res = await runSimulation(body)
      setRevealedCount(0)
      setResult(res)
    } catch (e) {
      setRunError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (backendError) {
    return (
      <div className="rounded-md border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
        Could not reach the live simulator backend at <code>localhost:8000</code> ({backendError}). Start it with{' '}
        <code className="rounded bg-rose-100 px-1">uvicorn api.main:app --reload --port 8000</code> from the repo root, then reload this
        page. Batch Results, Story, and Decision Trace still work without it - they read saved files.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-600">
        This tab calls the real backend pipeline live - classify, priors, funding window, allocate, decision, explain - on whatever
        payment you pick or build below. It never touches the real Razorpay API. Everything else in this dashboard (Story, Decision
        Trace, Batch Results) reads pre-computed files; this is the one place that computes something in front of you.
      </p>

      <div className="flex gap-1 border-b border-slate-200">
        <button
          onClick={() => setMode('persona')}
          className={`px-3 py-1.5 text-sm ${mode === 'persona' ? 'border-b-2 border-blue-600 font-medium text-blue-700' : 'text-slate-500'}`}
        >
          Pick a scenario
        </button>
        <button
          onClick={() => setMode('custom')}
          className={`px-3 py-1.5 text-sm ${mode === 'custom' ? 'border-b-2 border-blue-600 font-medium text-blue-700' : 'text-slate-500'}`}
        >
          Try your own
        </button>
      </div>

      {mode === 'persona' && (
        <div className="grid gap-3 sm:grid-cols-2">
          {personas.map((p) => (
            <PersonaCard key={p.key} persona={p} selected={selectedPersonaKey === p.key} onSelect={setSelectedPersonaKey} />
          ))}
        </div>
      )}

      {mode === 'custom' && (
        <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">Amount (paise)</span>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <div className="flex items-end gap-2 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={useRawError} onChange={(e) => setUseRawError(e.target.checked)} />
                Paste raw error JSON instead of picking a cause
              </label>
            </div>
          </div>

          {!useRawError ? (
            <label className="block text-sm">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">Failure cause</span>
              <select
                value={cause}
                onChange={(e) => setCause(e.target.value)}
                className="mt-1 block w-full max-w-sm rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                {FAILURE_CAUSES.map((c) => (
                  <option key={c} value={c}>
                    {causeLabel(c)} ({c})
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="block text-sm">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Raw Razorpay-shaped error JSON - try breaking the classifier
              </span>
              <textarea
                value={rawErrorText}
                onChange={(e) => setRawErrorText(e.target.value)}
                rows={6}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs"
              />
            </label>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
                Prior debits fell on this day of month (optional)
              </span>
              <input
                type="number"
                min="1"
                max="28"
                value={priorDebitDay}
                onChange={(e) => setPriorDebitDay(e.target.value)}
                placeholder="e.g. 5"
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block text-sm">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400"># of prior successful debits</span>
              <input
                type="number"
                min="0"
                value={nPriorDebits}
                onChange={(e) => setNPriorDebits(e.target.value)}
                className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
          </div>
          <p className="text-xs text-slate-400">
            Only affects `insufficient_funds` - feeds Stage 4's funding-window inference. Leave blank for a thin-history fallback case.
          </p>
        </div>
      )}

      <button
        onClick={handleRun}
        disabled={loading}
        className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? 'Running the real pipeline…' : 'Run this payment'}
      </button>

      {runError && <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{runError}</div>}

      {result && (
        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Pipeline execution, in order</h3>
            <StatusStrip traces={result.allocator_stage_traces} revealedCount={revealedCount} />
          </div>

          {result.decisions_differ && result.allocator_decision.action !== result.baseline_decision.action && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              The allocator and the fixed-schedule baseline disagree on this one: allocator chose{' '}
              <strong>{result.allocator_decision.action}</strong>, baseline would have chosen <strong>{result.baseline_decision.action}</strong>.
            </div>
          )}
          {result.decisions_differ && result.allocator_decision.action === result.baseline_decision.action && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
              Both chose to <strong>{result.allocator_decision.action}</strong>, but at different times - the allocator picked{' '}
              <strong>{result.allocator_decision.scheduled_at ? new Date(result.allocator_decision.scheduled_at).toLocaleString() : '—'}</strong>,
              baseline's fixed schedule would have picked{' '}
              <strong>{result.baseline_decision.scheduled_at ? new Date(result.baseline_decision.scheduled_at).toLocaleString() : '—'}</strong>.
            </div>
          )}

          {result.allocator_decision.cause === 'unknown' && (
            <div className="rounded-md border border-slate-300 bg-slate-50 p-3 text-sm text-slate-700">
              Shown honestly, not forced: the classifier couldn't confidently place this payload -{' '}
              <strong>cause=unknown, confidence={result.allocator_decision.cause_confidence}</strong>, routed to notify rather than a
              guessed retry.
            </div>
          )}

          <div className="flex gap-1 border-b border-slate-200">
            <button
              onClick={() => setResultTab('story')}
              className={`px-3 py-1.5 text-sm ${resultTab === 'story' ? 'border-b-2 border-blue-600 font-medium text-blue-700' : 'text-slate-500'}`}
            >
              This payment, as a story
            </button>
            <button
              onClick={() => setResultTab('trace')}
              className={`px-3 py-1.5 text-sm ${resultTab === 'trace' ? 'border-b-2 border-blue-600 font-medium text-blue-700' : 'text-slate-500'}`}
            >
              This payment, full trace
            </button>
          </div>

          {resultTab === 'story' && <StoryView payment={toPaymentShape(result)} isLive />}
          {resultTab === 'trace' && <DecisionTraceView payment={toPaymentShape(result)} />}
        </div>
      )}
    </div>
  )
}
