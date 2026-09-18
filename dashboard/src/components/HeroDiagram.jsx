import { useState } from 'react'
import { CAUSE_BRANCH, INTERVENTIONS } from '../lib/site.js'
import { causeLabel } from '../lib/format.js'

const CAUSES = ['insufficient_funds', 'bank_technical', 'afa_required', 'mandate_revoked']
const BRANCH = Object.fromEntries(INTERVENTIONS.map((i) => [i.key, i]))

// Click a failure reason and watch which of the three interventions it routes
// to. The mapping mirrors the saved batch run; the Live Simulator tab computes
// real decisions.
export default function HeroDiagram() {
  const [cause, setCause] = useState('insufficient_funds')
  const active = CAUSE_BRANCH[cause]

  return (
    <div className="rounded-xl border border-white/10 bg-[#0a1020] p-5 shadow-2xl">
      <div className="flex items-center justify-between">
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-slate-400">Payment failed · ₹1,499</p>
        <div className="flex gap-1.5" aria-label="Three retries available">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-3 w-3 rounded-sm border border-indigo-300/60 bg-indigo-400/30" />
          ))}
        </div>
      </div>

      <p className="mt-4 text-xs text-slate-400">Why did it fail? Pick one:</p>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {CAUSES.map((c) => (
          <button
            key={c}
            onClick={() => setCause(c)}
            className={`rounded-md border px-3 py-2 text-left text-[12.5px] leading-snug transition ${
              cause === c ? 'border-indigo-300 bg-indigo-400/15 text-white' : 'border-white/10 text-slate-300 hover:border-white/30'
            }`}
          >
            {causeLabel(c)}
          </button>
        ))}
      </div>

      <div className="mt-5 grid grid-cols-3 gap-2">
        {INTERVENTIONS.map((i) => {
          const on = i.key === active
          return (
            <div
              key={i.key}
              className="rounded-md border px-3 py-3 text-center transition"
              style={{
                borderColor: on ? i.color : 'rgba(255,255,255,0.1)',
                background: on ? `${i.color}22` : 'transparent',
                opacity: on ? 1 : 0.4,
              }}
            >
              <p className="text-[13px] font-semibold text-white">{i.label}</p>
            </div>
          )
        })}
      </div>
      <p className="mt-3 min-h-[2.5rem] text-[13px] leading-snug text-slate-300">{BRANCH[active].when}</p>
      <p className="mt-2 font-mono text-[11px] text-slate-500">The branch comes from a fixed lookup, not a model.</p>
    </div>
  )
}
