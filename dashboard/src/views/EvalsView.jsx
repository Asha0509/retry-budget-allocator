import { useJson } from '../lib/useJson.js'
import { DOCS, REPO } from '../lib/site.js'
import ExplanationEvalPanel from './ExplanationEvalPanel.jsx'

function Card({ title, children, note }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <h3 className="font-semibold text-slate-900">{title}</h3>
      <div className="mt-2 text-sm leading-relaxed text-slate-700">{children}</div>
      {note && <p className="mt-3 text-[12px] text-slate-400">{note}</p>}
    </div>
  )
}

export default function EvalsView() {
  const ms = useJson('/data/multiseed.json')
  const ec = useJson('/data/economics.json')
  const dc = useJson('/data/data_contract.json')
  const m = ms.data, e = ec.data, c = dc.data

  return (
    <div className="space-y-6">
      <p className="max-w-3xl text-sm text-slate-600">
        Every figure below is read from a saved file produced by the eval harness. Nothing is recomputed in your browser, and all of it is
        measured under the declared outcome model, not on real customers.
      </p>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Is the gap stable across random seeds?" note="eval/results/multiseed.json">
          {m ? (
            <>
              <p>The fixed schedule recovered <span className="font-mono">{m.baseline_recovered_mean}</span> payments on average; the allocator <span className="font-mono">{m.allocator_recovered_mean}</span>.</p>
              <p className="mt-2">The allocator won on raw recoveries in <span className="font-mono">{m.n_seeds_where_allocator_wins_on_raw_recovery}</span> of <span className="font-mono">{m.n_seeds_total}</span> seeds. The gap is a property of the design, not of one draw.</p>
            </>
          ) : 'Loading…'}
        </Card>
        <Card title="When does saving attempts pay off?" note="eval/results/economics.json">
          {e ? (
            <>
              <p>Break-even at about <span className="font-mono">₹{Math.round(e.breakeven_cost_per_attempt_rupees)}</span> per attempt.</p>
              <p className="mt-2">Across a grid of customer-value and annoyance assumptions the allocator earns more money in <span className="font-mono">{Math.round(e.surface_fraction_allocator_wins * 100)}%</span> of cells. At the illustrative ₹{e.assumptions.gateway_cost_rupees} per attempt it does not, and we say so.</p>
            </>
          ) : 'Loading…'}
        </Card>
        <Card title="Is the input data valid?" note="eval/results/data_contract.json">
          {c ? (
            <>
              <p><span className="font-mono">{c.n.toLocaleString('en-IN')}</span> synthetic rows checked against five rules. Contract {c.passed ? 'passed' : 'FAILED'}.</p>
              <ul className="mt-2 list-disc pl-5 text-[13px]">
                {Object.entries(c.failing_rows_by_check).map(([k, v]) => (<li key={k}><span className="font-mono">{k}</span>: {v} failing</li>))}
              </ul>
            </>
          ) : 'Loading…'}
        </Card>
      </div>

      <div>
        <h3 className="mb-3 font-semibold text-slate-900">Is the written explanation faithful to the decision?</h3>
        <ExplanationEvalPanel />
      </div>

      <div>
        <h3 className="mb-3 font-semibold text-slate-900">Read the full write-ups</h3>
        <div className="flex flex-wrap gap-2">
          {DOCS.map((d) => (
            <a key={d.file} href={`${REPO}/blob/main/${d.file}`} target="_blank" rel="noreferrer" className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-indigo-400">{d.title}</a>
          ))}
        </div>
      </div>
    </div>
  )
}
