import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useJson } from '../lib/useJson.js'

// Reads eval/results/policy_whatif.json (copied to public/data) - the
// allocator's own knobs varied under the frozen outcome model (PRD Sec 5.2).
// Nothing is recomputed in the browser and the shipped defaults never change.

const SPACING_TEXT = {
  sooner: { label: 'Sooner', detail: 'after 12 hours, 2 days, 5 days', color: '#4338CA' },
  published: { label: 'Published practice', detail: 'after 1 day, 3 days, 7 days', color: '#0C9A86' },
  later: { label: 'Later', detail: 'after 2 days, 4 days, 7 days', color: '#B45309' },
}

const thresholdText = (t) => (t > 1 ? 'Never use the guess' : `${Math.round(t * 100)}% sure`)
const rupees = (v) => `₹${Math.round(v).toLocaleString('en-IN')}`

const oneDecimal = (v) => (Number.isInteger(v) ? String(v) : v.toFixed(1))

function Metric({ label, value, range, base, better = 'higher', fmt = oneDecimal }) {
  // Means of 10 seeds: round before comparing so float noise never prints.
  const diff = Math.round((value - base) * 10) / 10
  const good = better === 'higher' ? diff >= 0 : diff <= 0
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{fmt(value)}</p>
      <p className="text-xs text-slate-500">range across seeds {fmt(range.min)}–{fmt(range.max)}</p>
      <p className={`mt-1 text-xs font-medium ${good ? 'text-emerald-700' : 'text-rose-700'}`}>
        {diff === 0 ? 'same as' : `${diff > 0 ? '+' : '−'}${fmt(Math.abs(diff))} vs`} the fixed schedule ({fmt(base)})
      </p>
    </div>
  )
}

function Chart({ data }) {
  const rows = data.thresholds.map((t) => {
    const row = { t: thresholdText(t) }
    for (const p of data.points.filter((p) => p.confidence_threshold === t)) row[p.spacing] = p.recovered.mean
    return row
  })
  const values = [data.baseline.recovered.mean, ...data.points.map((p) => p.recovered.mean)]
  const domain = [Math.floor(Math.min(...values)) - 2, Math.ceil(Math.max(...values)) + 2]
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        Payments recovered (mean of {data.seeds.length} batches) by spacing and confidence needed
      </h3>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={rows} margin={{ top: 16, right: 24, left: 8, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="t" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={56} padding={{ left: 24, right: 8 }} />
          <YAxis tick={{ fontSize: 11 }} domain={domain} width={36} />
          <Tooltip formatter={(v, name) => [v, SPACING_TEXT[name]?.label ?? name]} />
          <Legend formatter={(name) => SPACING_TEXT[name]?.label ?? name} wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine y={data.baseline.recovered.mean} stroke="#475569" strokeDasharray="5 4"
            label={{ value: `fixed schedule ${data.baseline.recovered.mean}`, position: 'insideTopRight', fontSize: 11, fill: '#475569' }} />
          {Object.keys(data.spacings).map((s) => (
            <Line key={s} dataKey={s} stroke={SPACING_TEXT[s]?.color} strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default function WhatIfView() {
  const { loading, error, data } = useJson('/data/policy_whatif.json')
  const [spacing, setSpacing] = useState('published')
  const [ti, setTi] = useState(null)

  if (loading) return <div className="py-12 text-center text-slate-500">Loading the what-if study…</div>
  if (error) {
    return (
      <div className="py-12 text-center text-rose-600">
        Could not load the what-if results ({error.message}). Run <code className="rounded bg-rose-50 px-1">python -m eval.policy_whatif</code> and
        copy <code className="rounded bg-rose-50 px-1">eval/results/policy_whatif.json</code> into <code className="rounded bg-rose-50 px-1">dashboard/public/data/</code>.
      </div>
    )
  }

  const defaultIndex = data.thresholds.indexOf(data.default.confidence_threshold)
  const index = ti ?? defaultIndex
  const threshold = data.thresholds[index]
  const point = data.points.find((p) => p.spacing === spacing && p.confidence_threshold === threshold)
  const isDefault = spacing === data.default.spacing && threshold === data.default.confidence_threshold
  const b = data.baseline
  const conf = data.stage4_confidence

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">What if the allocator were set up differently?</h2>
        <p className="mt-1 text-sm text-slate-600">
          Two judgment calls are built into the allocator: <strong>when</strong> its three retries may happen, and{' '}
          <strong>how sure</strong> it must be about a customer's payday before timing a retry around it. Change them below. Each
          result is the average over {data.seeds.length} different batches of {data.n} failed payments, scored by the same frozen
          success model as everything else - precomputed, not run in your browser.
        </p>
      </div>

      <div className="grid gap-4 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-2">
        <fieldset>
          <legend className="text-xs font-semibold uppercase tracking-wide text-slate-400">When to retry</legend>
          <div className="mt-2 space-y-2">
            {Object.keys(data.spacings).map((s) => (
              <label key={s} className="flex cursor-pointer items-start gap-2 text-sm">
                <input type="radio" name="spacing" className="mt-1" checked={spacing === s} onChange={() => setSpacing(s)} />
                <span>
                  <span className="font-medium text-slate-800">{SPACING_TEXT[s]?.label ?? s}</span>
                  <span className="text-slate-500"> - {SPACING_TEXT[s]?.detail ?? data.spacings[s].join('h, ') + 'h'}</span>
                  {s === data.default.spacing && <span className="ml-1 rounded bg-slate-100 px-1.5 text-xs text-slate-600">shipped</span>}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <div>
          <label htmlFor="threshold" className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            How sure about payday before using it: <span className="normal-case text-slate-800">{thresholdText(threshold)}</span>
            {threshold === data.default.confidence_threshold && <span className="ml-1 rounded bg-slate-100 px-1.5 text-xs normal-case text-slate-600">shipped</span>}
          </label>
          <input id="threshold" type="range" min={0} max={data.thresholds.length - 1} step={1} value={index}
            onChange={(e) => setTi(Number(e.target.value))} className="mt-3 w-full accent-indigo-700"
            aria-valuetext={thresholdText(threshold)} />
          <div className="flex justify-between text-xs text-slate-400">
            <span>{thresholdText(data.thresholds[0])}</span><span>{thresholdText(data.thresholds[data.thresholds.length - 1])}</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Below this, the payday guess is ignored and the retries follow the spacing chosen above.
          </p>
        </div>
      </div>

      {point && (
        <>
          <p className="text-sm text-slate-700">
            {isDefault ? 'This is the shipped setting.' : 'Compared with the fixed schedule:'} The allocator recovers{' '}
            <strong>{point.recovered.mean}</strong> payments on average and matches or beats the fixed schedule in{' '}
            <strong>{point.seeds_matching_or_beating_baseline} of {data.seeds.length}</strong> batches, while spending{' '}
            <strong>{Math.round((1 - point.attempts_spent.mean / b.attempts_spent.mean) * 100)}% fewer</strong> retries. Rule violations
            across all batches: <strong className={point.compliance_violations ? 'text-rose-700' : 'text-emerald-700'}>{point.compliance_violations}</strong>.
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Payments recovered" value={point.recovered.mean} range={point.recovered} base={b.recovered.mean} />
            <Metric label="Money recovered" value={point.rupees_recovered.mean} range={point.rupees_recovered} base={b.rupees_recovered.mean} fmt={rupees} />
            <Metric label="Retries spent" value={point.attempts_spent.mean} range={point.attempts_spent} base={b.attempts_spent.mean} better="lower" />
            <Metric label="Retries that could never work" value={point.attempts_wasted.mean} range={point.attempts_wasted} base={b.attempts_wasted.mean} better="lower" />
          </div>
        </>
      )}

      <Chart data={data} />

      <div className="space-y-2 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-semibold">What this shows, read before quoting</p>
        <p>
          <strong>The payday threshold barely matters here.</strong> Of {conf.payments} "not enough money" failures, {conf.zero_confidence} have
          too little history to guess at all (confidence 0) and the rest score between {Math.round(conf.nonzero_min * 100)}% and{' '}
          {Math.round(conf.nonzero_max * 100)}%. Nothing lands in between, so every threshold up to {Math.round(conf.nonzero_min * 100)}%
          behaves the same, and switching the guess off entirely changes the average by less than one payment.
        </p>
        <p>
          <strong>Retry timing does matter</strong>, and sooner wins under this success model, because it assumes a temporary bank
          problem is most likely to clear in the first day or two. The shipped setting stays at the published 1 / 3 / 7 days on purpose: switching after seeing
          which setting scores best against the model the allocator is graded on would be tuning to the answer key.
        </p>
        <p>No setting closes the gap to the fixed schedule on average payments recovered; every setting uses far fewer retries and wastes none on payments that could never succeed.</p>
      </div>
    </div>
  )
}
