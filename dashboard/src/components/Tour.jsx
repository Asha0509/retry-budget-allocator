import { useEffect, useState } from 'react'
import { TOUR_STEPS } from '../lib/site.js'

/**
 * Docked app tour (PRD Sec 6.1): walks through the landing page and every
 * dashboard tab while the page stays visible. `goToPage` is supplied by App.
 */
export default function Tour({ open, onClose, goToPage }) {
  const [i, setI] = useState(0)
  const step = TOUR_STEPS[i]

  useEffect(() => {
    if (open) goToPage(step.page)
    // Navigate when the tour opens or the step changes, not on every parent render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, i])

  useEffect(() => {
    if (!open) setI(0)
  }, [open])

  if (!open) return null
  const last = i === TOUR_STEPS.length - 1
  return (
    <aside
      role="dialog"
      aria-label="App tour"
      className="fixed bottom-4 right-4 z-50 max-h-[calc(100vh-2rem)] w-[min(390px,calc(100vw-2rem))] overflow-auto rounded-xl bg-[#0b1220] p-4 text-white shadow-2xl ring-1 ring-white/15"
    >
      <div className="flex items-center justify-between font-mono text-[11px] uppercase tracking-wider text-slate-400">
        <span>App tour · {i + 1} of {TOUR_STEPS.length}</span>
        <button onClick={onClose} aria-label="Close tour" className="text-xl leading-none text-white hover:text-indigo-300">×</button>
      </div>
      <h2 className="mt-2 text-lg font-semibold">{step.title}</h2>
      <p className="mt-1 text-sm leading-snug text-slate-200">{step.what}</p>
      <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm leading-snug text-slate-300">
        {step.has.map((h) => <li key={h}>{h}</li>)}
      </ul>
      <div className="mt-4 flex justify-between gap-2">
        <button
          disabled={i === 0}
          onClick={() => setI(i - 1)}
          className="rounded-md border border-white/40 px-3 py-1.5 text-sm text-white hover:bg-white/10 disabled:opacity-40"
        >
          Back
        </button>
        <button
          onClick={last ? onClose : () => setI(i + 1)}
          className="rounded-md bg-indigo-400 px-4 py-1.5 text-sm font-medium text-slate-900 hover:bg-indigo-300"
        >
          {last ? 'Finish' : 'Next page'}
        </button>
      </div>
    </aside>
  )
}
