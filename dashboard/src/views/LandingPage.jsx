import HeroDiagram from '../components/HeroDiagram.jsx'
import { useJson } from '../lib/useJson.js'
import { formatMoney } from '../lib/format.js'
import { DOCS, INTERVENTIONS, INVARIANTS, REPO, STAGES } from '../lib/site.js'

// Snapshot of `pytest --collect-only -q`; update when the suite grows.
const TEST_COUNT = 431

function Section({ id, eyebrow, title, intro, children, tone = 'light' }) {
  const bg = tone === 'alt' ? 'bg-white' : 'bg-[#f8fafc]'
  return (
    <section id={id} className={`${bg} border-t border-slate-200 py-16`}>
      <div className="mx-auto max-w-6xl px-5 sm:px-6">
        <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-slate-500">{eyebrow}</p>
        <h2 className="mt-2 max-w-2xl text-[1.75rem] font-semibold leading-tight tracking-tight text-slate-900">{title}</h2>
        {intro && <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-slate-600">{intro}</p>}
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}

function Stat({ label, value, detail }) {
  return (
    <div className="p-5">
      <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-slate-500">{label}</p>
      <p className="mt-1.5 font-mono text-[28px] font-medium leading-none tabular-nums text-slate-900">{value}</p>
      <p className="mt-2 text-[12.5px] leading-snug text-slate-500">{detail}</p>
    </div>
  )
}

export default function LandingPage({ run, onEnterDashboard }) {
  const multiseed = useJson('/data/multiseed.json').data
  const economics = useJson('/data/economics.json').data
  const base = run?.results_table?.baseline
  const alloc = run?.results_table?.allocator
  const saved = base && alloc ? base.attempts_spent - alloc.attempts_spent : null
  const savedPct = saved !== null ? Math.round((saved / base.attempts_spent) * 100) : null
  const branchCounts = run
    ? run.payments.reduce((m, p) => ({ ...m, [p.allocator_decisions[0].action]: (m[p.allocator_decisions[0].action] ?? 0) + 1 }), {})
    : {}

  return (
    <div style={{ fontFamily: 'var(--font-display)' }} className="min-h-screen bg-[#f8fafc] text-slate-900">
      <header className="sticky top-0 z-20 border-b border-white/10 bg-[#0b1220]/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3 sm:px-6">
          <span className="font-semibold text-white">Retry Budget Allocator</span>
          <nav className="flex items-center gap-4 text-sm text-slate-300">
            <a className="hidden hover:text-white sm:inline" href="#how">How it works</a>
            <a className="hidden hover:text-white sm:inline" href="#results">Results</a>
            <a className="hidden hover:text-white sm:inline" href="#honest">What is real</a>
            <a className="hidden hover:text-white sm:inline" href="#docs">Docs</a>
            <button onClick={() => onEnterDashboard('guide')} className="rounded-md bg-indigo-400 px-3 py-1.5 text-[13px] font-medium text-slate-900 hover:bg-indigo-300">
              Take the tour
            </button>
          </nav>
        </div>
      </header>

      <div className="bg-[#0b1220]">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-16 sm:px-6 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-slate-400">Recurring payment recovery for UPI AutoPay</p>
            <h1 className="mt-4 text-[2.25rem] font-semibold leading-[1.1] tracking-tight text-white sm:text-[2.75rem]">
              Three retries. <span className="text-indigo-300">Spend them on purpose.</span>
            </h1>
            <p className="mt-5 max-w-lg text-[15.5px] leading-relaxed text-slate-300">
              When a recurring payment fails, the rules give a business exactly three more attempts. A fixed schedule spends them
              without asking why it failed. This works out the reason first, then chooses to ask the customer, retry at a legal,
              well-timed moment, or stop.
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <button onClick={() => onEnterDashboard('live')} className="rounded-md bg-indigo-400 px-5 py-3 text-sm font-medium text-slate-900 hover:bg-indigo-300">
                Try a failed payment
              </button>
              <button onClick={() => onEnterDashboard('guide')} className="rounded-md border border-white/25 px-5 py-3 text-sm font-medium text-white hover:bg-white/10">
                Take the 3-minute tour
              </button>
            </div>
            <p className="mt-5 max-w-lg font-mono text-[11.5px] leading-relaxed text-slate-500">
              Results are from a simulation under a stated outcome model, not real recovery rates.
            </p>
          </div>
          <HeroDiagram />
        </div>
      </div>

      <Section id="how" eyebrow="How it decides" title="Seven stages, six of them plain code" intro="Every stage returns a trace you can open. Only the last one uses a language model, and it never decides anything." tone="alt">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map((s) => (
            <div key={s.n} className={`rounded-lg border bg-white p-4 ${s.ai ? 'border-indigo-300' : 'border-slate-200'}`}>
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded bg-indigo-600 font-mono text-xs text-white">{s.n}</span>
                <h3 className="font-semibold">{s.name}</h3>
                {s.ai && <span className="ml-auto rounded bg-indigo-100 px-1.5 py-0.5 font-mono text-[10px] text-indigo-700">AI</span>}
              </div>
              <p className="mt-2 text-[13.5px] leading-snug text-slate-700">{s.plain}</p>
              <p className="mt-2 text-[12px] leading-snug text-slate-500">{s.tech}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="interventions" eyebrow="Three real choices" title="Not a scheduler: it picks the right intervention" intro="If everything collapsed into retry-later this would only be a timer. In the saved batch all three branches fire.">
        <div className="grid gap-4 sm:grid-cols-3">
          {INTERVENTIONS.map((i) => (
            <div key={i.key} className="rounded-lg border border-slate-200 bg-white p-5" style={{ borderTop: `3px solid ${i.color}` }}>
              <p className="font-mono text-3xl font-medium tabular-nums">{branchCounts[i.key] ?? '–'}</p>
              <p className="mt-1 font-semibold">{i.label}</p>
              <p className="mt-2 text-[13.5px] leading-snug text-slate-600">{i.when}</p>
            </div>
          ))}
        </div>
        {run && <p className="mt-3 font-mono text-[12px] text-slate-400">Of {run.n} synthesized failed payments, first decision per payment.</p>}
      </Section>

      <Section id="results" eyebrow="Measured, stated plainly" title="Half the attempts, fewer recoveries, and where it breaks even" intro="The allocator wastes nothing on payments that cannot succeed. On raw recoveries the fixed schedule still wins, and we report that." tone="alt">
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="grid grid-cols-2 divide-slate-200 sm:grid-cols-4 sm:divide-x">
            <Stat label="Attempts saved" value={saved ?? '–'} detail={savedPct !== null ? `${savedPct}% fewer than a fixed schedule (${alloc.attempts_spent} vs ${base.attempts_spent})` : 'loading'} />
            <Stat label="Wasted attempts" value={alloc ? alloc.attempts_wasted_on_unrecoverable_causes : '–'} detail={base ? `vs ${base.attempts_wasted_on_unrecoverable_causes} for the fixed schedule` : ''} />
            <Stat label="Payments recovered" value={alloc && base ? `${alloc.payments_recovered} / ${base.payments_recovered}` : '–'} detail="Allocator / fixed schedule. The fixed schedule wins here." />
            <Stat label="Compliance violations" value={alloc ? alloc.compliance_violations : '–'} detail="Checked on every scheduled attempt." />
          </div>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">Across {multiseed?.n_seeds_total ?? 10} random seeds</p>
            <p className="mt-2 text-[14px] leading-snug text-slate-700">
              The allocator beat the fixed schedule on raw recoveries in{' '}
              <span className="font-mono font-semibold">{multiseed?.n_seeds_where_allocator_wins_on_raw_recovery ?? '–'}</span> of{' '}
              {multiseed?.n_seeds_total ?? '–'}. The gap is real, not one unlucky draw.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">Break-even cost per attempt</p>
            <p className="mt-2 text-[14px] leading-snug text-slate-700">
              If one attempt costs more than about{' '}
              <span className="font-mono font-semibold">₹{economics ? Math.round(economics.breakeven_cost_per_attempt_rupees) : '–'}</span>, saving attempts beats extra recoveries.
              Below that, the fixed schedule earns more.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <p className="font-mono text-[11px] uppercase tracking-wide text-slate-500">Money recovered</p>
            <p className="mt-2 text-[14px] leading-snug text-slate-700">
              {alloc && base ? `${formatMoney(alloc.amount_recovered_paise)} vs ${formatMoney(base.amount_recovered_paise)}` : '–'} in the simulated batch. {TEST_COUNT} automated tests guard the rules.
            </p>
          </div>
        </div>
        <button onClick={() => onEnterDashboard('batch')} className="mt-5 text-sm font-medium text-indigo-700 underline underline-offset-2">
          Open the full batch results and sensitivity sweep
        </button>
      </Section>

      <Section id="rules" eyebrow="Non-negotiable" title="Three rules it cannot break" intro="They are enforced in code, tested before anything else was built, and re-checked live in the dashboard.">
        <div className="grid gap-4 sm:grid-cols-3">
          {INVARIANTS.map((r) => (
            <div key={r.title} className="rounded-lg border border-slate-200 bg-white p-5">
              <h3 className="font-semibold">{r.title}</h3>
              <p className="mt-2 text-[13.5px] leading-snug text-slate-700">{r.plain}</p>
              <p className="mt-2 font-mono text-[11.5px] text-slate-500">{r.tech}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section id="ai" eyebrow="AI where it helps" title="The model explains. It never decides." tone="alt" intro="If the model provider is down, the explanation falls back to a template and the decision is identical.">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-5">
            <h3 className="font-semibold">Plain code decides</h3>
            <p className="mt-2 text-[13.5px] leading-snug text-slate-600">Why it failed, whether to retry, when to retry and when to stop are lookups and arithmetic you can audit.</p>
          </div>
          <div className="rounded-lg border border-indigo-300 bg-white p-5">
            <h3 className="font-semibold">A model writes the words</h3>
            <p className="mt-2 text-[13.5px] leading-snug text-slate-600">Stage 7 turns the decision into a reason and a customer message in English and Hinglish, cached with the run.</p>
          </div>
        </div>
      </Section>

      <Section id="honest" eyebrow="Read before quoting" title="What is real and what is simulated">
        <div className="grid gap-6 text-[14px] leading-relaxed text-slate-700 sm:grid-cols-2">
          <ul className="list-disc space-y-2 pl-5">
            <li>The pipeline runs live on any payment you build in the Live Simulator.</li>
            <li>The batch is 60 synthesized failed payments. The failure mix is modelled from published rates, not observed.</li>
            <li>Whether a retry succeeds is drawn from a frozen outcome model we wrote. The allocator never sees it.</li>
          </ul>
          <ul className="list-disc space-y-2 pl-5">
            <li>These are not real recovery rates. The claim is only that a scarce budget is spent well under a stated model.</li>
            <li>The Razorpay test API was tried for mandate creation; the large batch replays that captured schema locally.</li>
            <li>The funding window is inferred with a confidence score. Below the threshold it uses safe spacing.</li>
          </ul>
        </div>
      </Section>

      <Section id="docs" eyebrow="Go deeper" title="Documentation and evals" tone="alt">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {DOCS.map((d) => (
            <a key={d.file} href={`${REPO}/blob/main/${d.file}`} target="_blank" rel="noreferrer" className="rounded-lg border border-slate-200 bg-white p-5 hover:border-indigo-400">
              <h3 className="font-semibold">{d.title}</h3>
              <p className="mt-2 text-[13.5px] leading-snug text-slate-600">{d.note}</p>
            </a>
          ))}
          <button onClick={() => onEnterDashboard('evals')} className="rounded-lg border border-indigo-300 bg-white p-5 text-left hover:border-indigo-500">
            <h3 className="font-semibold">Evals in the dashboard</h3>
            <p className="mt-2 text-[13.5px] leading-snug text-slate-600">Seeds, economics, data contract and explanation quality, computed from saved artifacts.</p>
          </button>
        </div>
      </Section>

      <footer className="bg-[#0b1220] py-8">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 text-sm text-slate-400 sm:px-6">
          <span>Retry Budget Allocator · simulation study</span>
          <a className="underline" href={REPO} target="_blank" rel="noreferrer">Source on GitHub</a>
        </div>
      </footer>
    </div>
  )
}
